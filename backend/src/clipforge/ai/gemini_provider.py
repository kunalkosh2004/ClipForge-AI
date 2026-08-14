import asyncio
import json
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from google import genai
from google.genai import types
from pydantic import BaseModel

from clipforge.common import logging as logging_mod
from clipforge.common.errors import ProviderError
from clipforge.common.ports import (
    AIModelUsage,
    AIProvider,
    EditingBlueprint,
    EditingPlan,
    Transcript,
    TranscriptSegment,
    VideoInput,
    VideoUnderstanding,
    Word,
)
from clipforge.common.times import parse_timestamp
from clipforge.directing.domain.prompt import DIRECTOR_PROMPT

_FILE_ACTIVE_TIMEOUT_SECONDS = 120.0
_FILE_POLL_INTERVAL_SECONDS = 5.0

# Long audio is transcribed in short overlapping pieces so Gemini keeps
# reliable timestamps across the whole file: single-shot transcription of a
# multi-minute video drifts and drops whole sections (verified in prod: a
# 256s video produced a transcript with a 160s hole). Chunks cover
# ``_CHUNK_SECONDS`` and start every ``step`` seconds; the merge drops each
# chunk's first ``_CHUNK_OVERLAP`` seconds of words so there are no gaps or
# duplicates. Mirrors MotionCaption's GeminiTranscriptProvider.
_CHUNK_SECONDS = 45.0
_CHUNK_OVERLAP = 3.0
# A silent stretch this long between words means a chunk's speech was
# dropped; the transcript is repaired by re-transcribing just that window.
_GAP_FILL_THRESHOLD = 8.0
# Keep a little margin around a re-transcribed gap so cut-off words survive.
_GAP_FILL_MARGIN = 2.0
# Gemini stretches the end timestamp of a chunk's final word far past the
# real audio (observed: a 0.2s word spanning 40s). Spoken words never last
# this long; anything longer is a hallucinated end and gets capped so silent
# stretches stay visible to the gap detector.
_MAX_WORD_DURATION = 4.0

logger = logging_mod.get_logger(__name__)

UsageCallback = Callable[[AIModelUsage], Awaitable[None]]


class GeminiProvider(AIProvider):
    """Gemini REST API client built on the official `google-genai` SDK.

    Supports a fallback chain of API keys: each key gets its own `genai.Client`
    (and its own Gemini Files upload), and calls try the keys in order. A key
    that 401s/429s or otherwise fails is skipped for the next one, so quota
    exhaustion on one key doesn't kill the pipeline.

    Also supports a fallback chain of models: if a model fails (retired, quota,
    rate limit), the next model in the chain is tried.

    `VideoInput.storage_uri` may be either a Files API URI (https://...) which is
    used as-is, or a local filesystem path, in which case the video is uploaded
    to the Files API and its returned URI is used for analysis.
    """

    _DEFAULT_MODELS = ("gemini-flash-latest", "gemini-1.5-flash", "gemini-1.5-pro")

    def __init__(
        self,
        api_key: str,
        api_keys: list[str] | None = None,
        model: str | None = None,
        models: list[str] | None = None,
        on_usage: UsageCallback | None = None,
    ) -> None:
        keys = list(dict.fromkeys([api_key, *(api_keys or [])]))
        if not keys:
            raise ValueError("at least one Gemini API key is required")
        self._clients: dict[str, list[tuple[str, genai.Client]]] = {}
        model_chain = (
            models
            if models is not None
            else ([model] if model else list(self._DEFAULT_MODELS))
        )
        for model_name in model_chain:
            self._clients[model_name] = [
                (f"key-{i}", genai.Client(api_key=key)) for i, key in enumerate(keys, start=1)
            ]
        self._model_chain: list[str] = model_chain
        self._current_model = self._model_chain[0]
        self._last_key: str = self._clients[self._current_model][0][0]
        self._file_cache: dict[tuple[str, str, str], Any] = {}  # (model, key, uri) -> file
        self._on_usage = on_usage

    @property
    def MODEL(self) -> str:
        """Most recently used model (so callers can label the analysis)."""
        return self._current_model

    @property
    def KEY(self) -> str:
        """Label of the most recently used API key (key-1, key-2, ...)."""
        return self._last_key

    def _clients_for_model(self, model: str) -> list[tuple[str, genai.Client]]:
        return self._clients.get(model, [])

    def _client_for(self, model: str, key_label: str) -> genai.Client:
        for label, client in self._clients_for_model(model):
            if label == key_label:
                return client
        raise ProviderError(f"unknown Gemini API key label: {key_label} for model {model}")

    async def _resolve_file_part(self, video: VideoInput, model: str, key_label: str) -> Any:
        uri = video.storage_uri
        if uri.startswith(("https://", "http://")):
            return types.Part(file_data=types.FileData(file_uri=uri))
        cached = self._file_cache.get((model, key_label, uri))
        if cached is not None:
            return cached
        client = self._client_for(model, key_label)
        file_obj = await asyncio.to_thread(
            self._upload_and_wait, client, uri, video.mime_type
        )
        self._file_cache[(model, key_label, uri)] = file_obj
        return file_obj

    def _upload_and_wait(self, client: genai.Client, path: str, mime_type: str) -> Any:
        if not Path(path).exists():
            raise ProviderError(f"video file not found for upload: {path}")
        try:
            file_obj = client.files.upload(
                file=path,
                config=types.UploadFileConfig(mimeType=mime_type),
            )
        except Exception as exc:
            raise ProviderError(f"Gemini file upload failed: {str(exc)[:300]}") from exc

        deadline = time.monotonic() + _FILE_ACTIVE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                current = client.files.get(name=file_obj.name)
            except Exception as exc:
                raise ProviderError(
                    f"failed to check Gemini file state: {str(exc)[:300]}"
                ) from exc
            state = current.state.name
            if state == "ACTIVE":
                return current
            if state == "FAILED":
                raise ProviderError("Gemini failed to process the video file")
            time.sleep(_FILE_POLL_INTERVAL_SECONDS)
        raise ProviderError(
            f"Gemini file processing timed out after {_FILE_ACTIVE_TIMEOUT_SECONDS:.0f}s"
        )

    async def _generate(
        self,
        prompt: str,
        video: VideoInput | None = None,
        schema: type[BaseModel] | None = None,
        operation: str = "generate",
    ) -> dict[str, Any]:
        config_kwargs: dict[str, Any] = {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        }
        if schema is not None:
            config_kwargs["responseSchema"] = _schema_for_gemini(schema)

        last_error: ProviderError | None = None
        for model in self._model_chain:
            for key_label, _client in self._clients_for_model(model):
                try:
                    file_part = None
                    if video is not None:
                        file_part = await self._resolve_file_part(video, model, key_label)
                    contents = [prompt] if file_part is None else [file_part, prompt]
                    return await self._generate_once(
                        model, key_label, contents, config_kwargs, operation
                    )
                except ProviderError as exc:
                    logger.warning(
                        "gemini_key_failed",
                        key=key_label,
                        model=model,
                        error=str(exc)[:200],
                        operation=operation,
                    )
                    last_error = exc
                    # Check if this is a model-level error (not key-specific)
                    if self._is_model_error(exc):
                        break  # Try next model
        raise last_error or ProviderError("no Gemini API keys/models configured")

    def _is_model_error(self, exc: ProviderError) -> bool:
        """Determine if error is model-level (should try next model) vs key-level."""
        error_msg = str(exc).lower()
        # Model retired, not found, or quota exhausted for this model
        return any(keyword in error_msg for keyword in [
            "model not found",
            "model has been retired",
            "model is not supported",
            "unsupported model",
            "quota exhausted for model",
            "model quota",
            "quota exhausted for metric",
            "generate_content_free_tier_requests",
            "quota failure",
            "resource_exhausted",
        ])

    async def _generate_once(
        self,
        model: str,
        key_label: str,
        contents: list[Any],
        config_kwargs: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        def _call() -> Any:
            client = self._client_for(model, key_label)
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )

        try:
            response = await asyncio.to_thread(_call)
            text = response.text
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Gemini request failed: {str(exc)[:300]}") from exc
        if not text:
            raise ProviderError("Gemini returned an empty response")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("Gemini returned non-JSON output") from exc
        if not isinstance(parsed, dict):
            raise ProviderError("Gemini response JSON was not an object")
        self._current_model = model
        self._last_key = key_label
        await self._record_usage(response, operation, key_label, model)
        return parsed

    async def _record_usage(
        self, response: Any, operation: str, key_label: str, model: str
    ) -> None:
        if self._on_usage is None:
            return
        meta = getattr(response, "usage_metadata", None)
        if meta is None:
            return
        usage = AIModelUsage(
            model=model,
            operation=operation,
            prompt_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
            response_tokens=int(getattr(meta, "response_token_count", 0) or 0),
            total_tokens=int(getattr(meta, "total_token_count", 0) or 0),
            key=key_label,
        )
        try:
            await self._on_usage(usage)
        except Exception:
            # usage recording must never break the pipeline
            logger.exception("ai_usage_record_failed", operation=operation)

    async def analyze_video(self, video: VideoInput) -> VideoUnderstanding:
        data = await self._generate(
            "Describe the video: scenes (start, end, description, shot_type), "
            "topics, and sentiment (-1 to +1). Use numeric seconds for start and end.",
            video=video,
            schema=VideoUnderstanding,
            operation="analyze_video",
        )
        data = _coerce_scene_times(data)
        return VideoUnderstanding.model_validate(data)

    async def transcribe(self, video: VideoInput) -> Transcript:
        """Word-timestamped transcript with speaker labels.

        Short media (<= ``_CHUNK_SECONDS``) is transcribed in one call. Longer
        media is split into overlapping audio chunks that are transcribed
        separately and merged with offsets — Gemini's per-file timestamps
        drift on multi-minute inputs, which silently drops whole sections of
        speech and desyncs the captions.
        """
        if video.duration_seconds is None or video.duration_seconds <= _CHUNK_SECONDS:
            return await self._transcribe_single(video)
        return await self._transcribe_chunked(video)

    async def _transcribe_single(self, video: VideoInput) -> Transcript:
        data = await self._generate(
            "Transcribe the speech: language and segments, each with text, start, end, "
            "speaker, and words (text, start, end). Use numeric seconds.",
            video=video,
            schema=Transcript,
            operation="transcribe",
        )
        return Transcript.model_validate(data)

    async def _transcribe_chunked(self, video: VideoInput) -> Transcript:
        """Split the media's audio into overlapping chunks, transcribe each,
        and stitch the results into one continuous transcript."""
        source = Path(video.storage_uri)
        if not source.is_file():
            raise ProviderError(
                f"chunked transcription needs a local media file, got: {source}"
            )
        with tempfile.TemporaryDirectory(prefix="clipforge-transcribe-") as td:
            scratch = Path(td)
            audio_path = scratch / "audio.wav"
            await self._extract_audio(source, audio_path)
            chunks = await self._split_audio(
                audio_path, scratch, video.duration_seconds
            )
            chunk_transcripts: list[Transcript] = []
            for chunk in chunks:
                chunk_input = video.model_copy(
                    update={
                        "storage_uri": str(chunk),
                        "mime_type": "audio/wav",
                        "duration_seconds": None,
                    }
                )
                chunk_transcripts.append(await self._transcribe_single(chunk_input))
            merged = _merge_chunk_transcripts(
                chunk_transcripts,
                chunk_seconds=_CHUNK_SECONDS,
                overlap_seconds=_CHUNK_OVERLAP,
            )
            # Gemini occasionally hallucinates timestamps past the end of a
            # short trailing chunk; clip them to the real media duration so
            # captions never outlive the video.
            if video.duration_seconds is not None:
                merged = _clamp_transcript_to_duration(
                    merged, video.duration_seconds
                )
            # Gemini occasionally drops the speech inside one chunk (returns
            # an empty or partial transcript for it). Re-transcribe just the
            # silent stretches so captions never jump the audio.
            gaps = _transcript_gaps(merged, threshold=_GAP_FILL_THRESHOLD)
            for gap_start, gap_end in gaps:
                fill_input = video.model_copy(
                    update={
                        "storage_uri": str(audio_path),
                        "mime_type": "audio/wav",
                        "duration_seconds": None,
                    }
                )
                gap_audio = await self._cut_audio(
                    audio_path,
                    scratch,
                    max(0.0, gap_start - _GAP_FILL_MARGIN),
                    min(video.duration_seconds or gap_end, gap_end + _GAP_FILL_MARGIN),
                )
                fill_input = fill_input.model_copy(
                    update={"storage_uri": str(gap_audio)}
                )
                try:
                    fill_transcript = await self._transcribe_single(fill_input)
                except ProviderError:
                    logger.warning("gap_fill_transcription_failed", gap_start=gap_start)
                    continue
                merged = _splice_fill_into_transcript(
                    merged,
                    fill_transcript,
                    gap_start=gap_start,
                    gap_end=gap_end,
                )
        return merged

    async def _cut_audio(
        self, audio_path: Path, out_dir: Path, start: float, end: float
    ) -> Path:
        """Cut ``[start, end)`` from the WAV into a fresh chunk file."""
        output = out_dir / f"gap_{start:.0f}_{end:.0f}.wav"
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{max(0.0, start):.3f}",
            "-t", f"{max(0.1, end - start):.3f}",
            "-i", str(audio_path),
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(output),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ProviderError(
                "gap-fill audio cut failed: "
                + (stderr or b"").decode(errors="replace")[:300]
            )
        return output

    async def _extract_audio(self, source: Path, output: Path) -> None:
        """Extract a mono 16 kHz WAV track for reliable chunked ASR."""
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(source),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(output),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ProviderError(
                "audio extraction failed: " + (stderr or b"").decode(errors="replace")[:300]
            )

    async def _split_audio(
        self, audio_path: Path, out_dir: Path, duration: float | None
    ) -> list[Path]:
        """Split the WAV into overlapping chunks (45s with 3s overlap)."""
        step = _CHUNK_SECONDS - _CHUNK_OVERLAP
        if duration is None or duration <= 0.0:
            raise ProviderError("cannot chunk audio without a known duration")
        chunks: list[Path] = []
        start = 0.0
        index = 0
        while start < duration - 1e-6:
            chunk = out_dir / f"chunk_{index:03d}.wav"
            cmd = [
                "ffmpeg", "-y", "-v", "error",
                "-ss", f"{start:.3f}",
                "-t", f"{_CHUNK_SECONDS:.3f}",
                "-i", str(audio_path),
                "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(chunk),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise ProviderError(
                    "audio chunking failed: "
                    + (stderr or b"").decode(errors="replace")[:300]
                )
            chunks.append(chunk)
            start += step
            index += 1
        return chunks

    async def generate_editing_plan(
        self,
        video: VideoInput,
        preset: str | None = None,
        context: VideoUnderstanding | None = None,
        editing_style: str | None = None,
    ) -> EditingPlan:
        prompt = (
            "You are an expert YouTube Shorts editor.\n\n"
            "Analyze the uploaded video carefully.\n\n"
            "Find the 5 most engaging moments.\n\n"
            "Each clip should be between 20 and 45 seconds.\n\n"
            "Return JSON with preset, style, thumbnail_text, and clips. Each clip has "
            "start_time, end_time (as MM:SS or seconds), hook, why_it_is_engaging, "
            "viral_score (0-100), emotion, category, and these optional per-clip fields:\n"
            "  - emphasis_times: list of 1-4 clip-local seconds (0 = clip start) where "
            "a punch/emphasis zoom and SFX should land; keep them inside the clip.\n"
            "  - emoji_triggers: list of {\"emoji\", \"time\"} pairs; emoji is one short "
            "emoji (or short emoji text), time is clip-local.\n"
            "  - cta_text: short call-to-action phrase (max 4 words) for this clip, or "
            "omit it.\n"
            "  - hook_text: on-screen headline (max 40 chars), distinct from hook.\n"
            "The top-level style object maps the editing feel to concrete directives; "
            "use it to fill caption_style (one of: karaoke, typewriter, fade, pop), "
            "caption_colors (list of up to 3 hex colors, no #), transition_style (cut, "
            "fade, slide, zoom), sfx_enabled, sfx_types (whoosh, boom), music_mood "
            "(energetic, chill, suspense, upbeat), music_volume_db, emojis_enabled, "
            "punch_zooms, zoom_intensity (0.0-1.0), cta_enabled, cta_text. Leave fields "
            "you are not confident about omitted.\n"
            "Example clip:\n"
            '{"start_time": "01:20", "end_time": "01:52", "hook": "This mistake changed '
            'everything", "why_it_is_engaging": "Emotional storytelling with suspense.", '
            '"viral_score": 95, "emotion": "Surprise", "category": "Storytelling", '
            '"emphasis_times": [4.0, 12.5], "emoji_triggers": [{"emoji": "\\u26a1", '
            '"time": 4.0}], "hook_text": "ONE mistake changed EVERYTHING", '
            '"cta_text": "Follow for more"}'
        )
        if editing_style:
            prompt += (
                "\n\nThe creator requested this editing style; map it to the style "
                "object and per-clip fields above:\n"
                f"{editing_style}"
            )
        if context is not None:
            prompt += (
                "\n\nScene and topic analysis already extracted from this video; "
                "ground your clip boundaries and hooks in it:\n"
                f"{context.model_dump_json()}"
            )
        data = await self._generate(
            prompt,
            video=video,
            schema=EditingPlan,
            operation="generate_editing_plan",
        )
        return EditingPlan.model_validate(data)

    async def direct(
        self,
        video: VideoInput,
        preset: str | None = None,
        context: VideoUnderstanding | None = None,
        editing_style: str | None = None,
    ) -> EditingBlueprint:
        prompt = DIRECTOR_PROMPT
        if editing_style:
            prompt += (
                "\n\nThe creator requested this editing style; honor it in the "
                "global_style and timeline events:\n"
                f"{editing_style}"
            )
        if context is not None:
            prompt += (
                "\n\nScene and topic analysis already extracted from this video; "
                "ground your scene boundaries, hooks, and emphasis timing in it:\n"
                f"{context.model_dump_json()}"
            )
        data = await self._generate(
            prompt,
            video=video,
            schema=EditingBlueprint,
            operation="direct",
        )
        return EditingBlueprint.model_validate(data)


def _merge_chunk_transcripts(
    transcripts: list[Transcript],
    *,
    chunk_seconds: float,
    overlap_seconds: float,
) -> Transcript:
    """Stitch per-chunk transcripts back into one continuous transcript.

    Chunk ``i`` covers ``[i*step, i*step+chunk_seconds)`` where ``step =
    chunk_seconds - overlap_seconds``, so its first ``overlap_seconds`` of
    words re-transcribe the tail of chunk ``i-1``. Discarding that head (and
    offsetting the rest) yields gapless, duplicate-free speech order.
    """
    if not transcripts:
        return Transcript(language="en", segments=[])
    step = chunk_seconds - overlap_seconds
    segments: list[TranscriptSegment] = []
    for index, transcript in enumerate(transcripts):
        offset = index * step
        for segment in transcript.segments:
            # The chunk's first overlap_seconds (local time) re-transcribe the
            # tail of the previous chunk; drop them so speech stays continuous.
            if index > 0 and segment.start < overlap_seconds:
                continue
            words = [
                Word(
                    text=word.text,
                    start=round(word.start + offset, 6),
                    end=round(word.end + offset, 6),
                )
                for word in segment.words
            ]
            segments.append(
                TranscriptSegment(
                    text=segment.text,
                    start=round(segment.start + offset, 6),
                    end=round(segment.end + offset, 6),
                    speaker=segment.speaker,
                    words=words,
                )
            )
    # Gemini sometimes stretches a chunk's final word end across the silent
    # tail (e.g. a 0.2s word spanning 40s). Cap implausibly long words so
    # the stretched end can't hide a real gap from the gap detector below.
    capped_segments: list[TranscriptSegment] = []
    for segment in segments:
        words = []
        for word in segment.words:
            if word.end - word.start > _MAX_WORD_DURATION:
                word = Word(
                    text=word.text,
                    start=word.start,
                    end=round(word.start + _MAX_WORD_DURATION, 6),
                )
            words.append(word)
        if words:
            capped_segments.append(
                TranscriptSegment(
                    text=segment.text,
                    start=segment.start,
                    end=segment.end,
                    speaker=segment.speaker,
                    words=words,
                )
            )
    language = next((t.language for t in transcripts if t.language), "en")
    return Transcript(language=language, segments=capped_segments)


def _clamp_transcript_to_duration(
    transcript: Transcript, duration: float
) -> Transcript:
    """Drop words that start past the media end and clamp trailing ends."""
    if duration <= 0:
        return transcript
    kept: list[Word] = []
    for segment in transcript.segments:
        for word in segment.words:
            if word.start >= duration:
                continue
            kept.append(
                Word(
                    text=word.text,
                    start=word.start,
                    end=min(word.end, duration),
                )
            )
    if not kept:
        return Transcript(language=transcript.language, segments=[])
    kept.sort(key=lambda w: (w.start, w.text))
    segments: list[TranscriptSegment] = []
    run: list[Word] = []
    for word in kept:
        if run and word.start - run[-1].end > 0.8:
            segments.append(_segment_from_words(run))
            run = []
        run.append(word)
    if run:
        segments.append(_segment_from_words(run))
    return Transcript(language=transcript.language, segments=segments)


def _transcript_gaps(
    transcript: Transcript, *, threshold: float
) -> list[tuple[float, float]]:
    """Silent stretches between consecutive words (``(prev_end, next_start)``)."""
    words = [word for seg in transcript.segments for word in seg.words]
    words.sort(key=lambda w: w.start)
    gaps: list[tuple[float, float]] = []
    for previous, current in zip(words, words[1:], strict=False):
        gap = current.start - previous.end
        if gap > threshold:
            gaps.append((previous.end, current.start))
    return gaps


def _splice_fill_into_transcript(
    transcript: Transcript,
    fill: Transcript,
    *,
    gap_start: float,
    gap_end: float,
) -> Transcript:
    """Replace a silent gap with the words from a re-transcribed window.

    Drops every existing word that overlaps the silent stretch ``[gap_start,
    gap_end]`` (the margin was already baked into the re-cut audio, so the
    fill carries the boundary words), keeps everything else, inserts the
    fill's words, and returns a sorted, continuous transcript.
    """
    kept = [
        word
        for seg in transcript.segments
        for word in seg.words
        if word.end <= gap_start or word.start >= gap_end
    ]
    fill_words = [word for seg in fill.segments for word in seg.words]
    merged = kept + fill_words
    merged.sort(key=lambda w: (w.start, w.text))

    if not merged:
        return Transcript(language=transcript.language, segments=[])
    # Rebuild segments from consecutive words (one segment per gap-separated run).
    segments: list[TranscriptSegment] = []
    run: list[Word] = []
    for word in merged:
        if run and word.start - run[-1].end > 0.8:
            segments.append(_segment_from_words(run))
            run = []
        run.append(word)
    if run:
        segments.append(_segment_from_words(run))
    return Transcript(language=transcript.language, segments=segments)


def _segment_from_words(words: list[Word]) -> TranscriptSegment:
    text = " ".join(word.text for word in words)
    return TranscriptSegment(
        text=text,
        start=round(words[0].start, 6),
        end=round(words[-1].end, 6),
        words=[word for word in words],
    )


def _coerce_scene_times(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize scene start/end to numeric seconds (Gemini may return MM:SS strings)."""
    for scene in data.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        for key in ("start", "end"):
            if key in scene:
                scene[key] = parse_timestamp(scene[key])
    return data


def _schema_for_gemini(schema: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema stripped for the Gemini Developer API.

    Pydantic emits `additionalProperties` for `dict`-typed fields, which the
    Gemini Developer API rejects (it's an Enterprise Agent Platform feature).
    Strip the key recursively so `responseSchema` works for any blueprint.
    """
    return cast(dict[str, Any], _strip_additional_properties(schema.model_json_schema()))


def _strip_additional_properties(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: _strip_additional_properties(value)
            for key, value in node.items()
            if key != "additionalProperties"
        }
    if isinstance(node, list):
        return [_strip_additional_properties(value) for value in node]
    return node
