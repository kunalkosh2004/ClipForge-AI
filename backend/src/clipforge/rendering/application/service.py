import asyncio
import shutil
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from clipforge.analysis.domain.ports import (
    AnalysisResultRepository,
    TranscriptRepository,
)
from clipforge.analysis.domain.presets import format_for_preset, get_preset
from clipforge.artifacts.domain.ports import ArtifactRepository, ArtifactStore
from clipforge.clips.domain.entities import Clip
from clipforge.clips.domain.ports import ClipRepository, ThumbnailGenerator
from clipforge.common import logging as logging_mod
from clipforge.common.ports import StorageProvider
from clipforge.lyrics.application.ass import build_motion_caption_ass
from clipforge.lyrics.application.blueprint import caption_theme_hint
from clipforge.lyrics.application.frames import build_motion_caption_frames
from clipforge.plugins.application.compile import compile_clip_events
from clipforge.plugins.application.pipeline import PluginRenderPipeline
from clipforge.plugins.domain.registry import (
    PluginRegistry,
    build_default_registry,
)
from clipforge.plugins.domain.spec import RenderContext
from clipforge.processing.domain.ports import StatusNotifier
from clipforge.processing.infrastructure.ffprobe import (
    build_metadata,
    download_to_tempfile,
    run_ffprobe,
)
from clipforge.rendering.domain.composite import CompositeRenderer
from clipforge.rendering.domain.formats import canvas_for_format
from clipforge.rendering.domain.framing import (
    FramingPlan,
    build_crop_expressions,
    crop_window_for_target,
    fit_points,
)
from clipforge.rendering.domain.ports import CaptionRenderer, FramingAnalyzer
from clipforge.rendering.domain.overlays import OverlayEngine
from clipforge.rendering.domain.styles import RenderStyle, apply_style_overrides
from clipforge.rendering.application.frames_overlays import (
    rasterize_overlays_into_frames,
)
from clipforge.rendering.infrastructure.audio_assets import (
    generate_music_bed,
    generate_sfx,
)
from clipforge.rendering.infrastructure.face_analyzer import detect_face_boxes
from clipforge.videos.domain.ports import VideoRepository

logger = logging_mod.get_logger(__name__)

DEFAULT_PRESET = "default"

CAPTION_RENDER_FPS = 30


class RenderingService:
    def __init__(
        self,
        clips: ClipRepository,
        transcripts: TranscriptRepository,
        analysis_results: AnalysisResultRepository,
        videos: VideoRepository,
        storage: StorageProvider,
        renderer: CaptionRenderer,
        thumbnails: ThumbnailGenerator,
        notifier: StatusNotifier,
        framing: FramingAnalyzer | None = None,
        artifacts: ArtifactRepository | None = None,
        artifact_store: ArtifactStore | None = None,
        caption_engine: str = "legacy",
        plugins: PluginRegistry | None = None,
    ) -> None:
        self._clips = clips
        self._transcripts = transcripts
        self._analysis_results = analysis_results
        self._videos = videos
        self._storage = storage
        self._renderer = renderer
        self._thumbnails = thumbnails
        self._notifier = notifier
        self._framing = framing
        self._artifacts = artifacts
        self._artifact_store = artifact_store
        self._caption_engine = caption_engine
        self._pipeline = PluginRenderPipeline(plugins or build_default_registry())

    async def render_clips_with_captions(self, video_id: uuid.UUID) -> tuple[int, int]:
        """Render captions, beat-timed zooms, and audio effects into every
        ready clip.

        Returns (rendered, skipped_without_words). A clip whose render fails
        keeps its raw cut — the failure is logged and processing continues.
        """
        page = await self._clips.list_for_video(video_id)
        clips = list(page.items)
        words = await self._transcript_words(video_id)

        analysis = await self._analysis_results.get_by_video_id(video_id)
        preset = (
            str((analysis.editing_plan or {}).get("preset") or DEFAULT_PRESET)
            if analysis is not None
            else DEFAULT_PRESET
        )
        clip_format = format_for_preset(preset)

        # Get style config from preset, then layer the AI's plan-level directives
        preset_obj = get_preset(preset)
        style = RenderStyle.from_preset(preset_obj) if preset_obj else RenderStyle()
        overrides = (analysis.editing_plan or {}).get("style") if analysis else None
        if isinstance(overrides, dict):
            style = apply_style_overrides(style, overrides)
        sfx_kind = _sfx_kind(overrides)

        # The AI Director's blueprint is the richest caption direction; its
        # subtitle theme (colors/animation) wins over preset + editor style.
        blueprint = analysis.editing_blueprint if analysis is not None else None
        caption_hint = caption_theme_hint(blueprint)
        caption_updates: dict[str, Any] = {}
        if caption_hint.accent_color:
            caption_updates["active_color"] = caption_hint.accent_color
        if caption_hint.muted_color:
            caption_updates["muted_color"] = caption_hint.muted_color
        if caption_hint.outline_color:
            caption_updates["outline_color"] = caption_hint.outline_color
        if caption_hint.animation:
            caption_updates["animation"] = caption_hint.animation
        if caption_updates:
            style = replace(style, caption=replace(style.caption, **caption_updates))

        beats = await self._beat_times(video_id)
        punch_ins = await self._timeline_punch_ins(video_id)

        scratch_dir = Path(tempfile.mkdtemp(prefix=f"render-{video_id}-"))
        rendered = 0
        skipped = 0
        failures: list[str] = []
        try:
            for clip in clips:
                if clip.status != "ready" or not clip.storage_key:
                    continue
                try:
                    path, _, _ = await download_to_tempfile(self._storage, clip.storage_key)
                except Exception as exc:
                    logger.warning(
                        "render_download_failed",
                        clip_id=str(clip.id),
                        error=str(exc)[:200],
                    )
                    failures.append(str(clip.id))
                    continue
                try:
                    canvas = await self._canvas_for_clip(path, clip_format)
                    if canvas is None:
                        logger.warning(
                            "render_canvas_unknown",
                            clip_id=str(clip.id),
                        )
                        continue
                    await self._render_clip_plugin(
                        clip,
                        path,
                        words,
                        canvas,
                        scratch_dir,
                        style,
                        preset,
                        beats,
                        sfx_kind,
                        punch_ins,
                        blueprint=blueprint,
                        caption_theme=caption_hint.theme,
                        caption_highlight_words=caption_hint.highlight_words,
                    )
                    rendered += 1
                except Exception:
                    logger.exception("render_failed", clip_id=str(clip.id))
                    failures.append(str(clip.id))
                finally:
                    path.unlink(missing_ok=True)
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)

        if failures:
            raise RuntimeError(
                f"render failed for {len(failures)} clip(s): {','.join(failures)}"
            )

        await self._notify_rendered(video_id, rendered, skipped)
        return rendered, skipped

    async def _beat_times(self, video_id: uuid.UUID) -> list[float]:
        video = await self._videos.get_by_id(video_id)
        if video is None or not video.metadata_json:
            return []
        audio = video.metadata_json.get("audio") or {}
        return [float(t) for t in audio.get("peaks", [])]

    async def _timeline_punch_ins(self, video_id: uuid.UUID) -> list[dict[str, Any]]:
        """Punch-ins from the timeline artifact (source-time seconds).

        Empty when the timeline artifact has not been computed or the
        render service is not wired to artifact storage — rendering then
        falls back to legacy beat + AI emphasis.
        """
        if self._artifacts is None or self._artifact_store is None:
            return []
        artifact = await self._artifacts.get_latest(video_id, "timeline")
        if artifact is None:
            return []
        payload = await self._artifact_store.read_payload(video_id, "timeline")
        if not payload:
            return []
        punch_ins = payload.get("punch_ins")
        return punch_ins if isinstance(punch_ins, list) else []

    async def _canvas_for_clip(
        self, source_path: Path, clip_format: str
    ) -> tuple[int, int] | None:
        """Output canvas for the clip: the preset's format canvas, or the
        source resolution when the format keeps the original aspect ratio."""
        canvas = canvas_for_format(clip_format)
        if canvas is not None:
            return canvas
        try:
            probe = await asyncio.to_thread(run_ffprobe, source_path)
            meta = build_metadata(probe)
            video = meta.get("video_stream") or {}
            width, height = video.get("width"), video.get("height")
        except Exception as exc:
            logger.warning("render_probe_failed", error=str(exc)[:200])
            return None
        if not width or not height:
            return None
        return (int(width), int(height))

    async def _render_clip(
        self,
        clip: Clip,
        source_path: Path,
        words: list[dict],
        canvas: tuple[int, int],
        scratch_dir: Path,
        style: RenderStyle,
        preset: str,
        beats: list[float],
        sfx_kind: str = "whoosh",
        punch_ins: list[dict[str, Any]] | None = None,
        caption_theme: str | None = None,
        caption_highlight_words: tuple[str, ...] = (),
    ) -> None:
        rendered_path = scratch_dir / f"rendered_{clip.id}.mp4"
        framing_plan = await self._framing_plan(source_path, canvas)

        faces: tuple[tuple[float, float, float, float], ...] = ()
        if self._caption_engine != "legacy":
            faces = tuple(
                await asyncio.to_thread(
                    detect_face_boxes, str(source_path), canvas, framing_plan
                )
            )

        # Beat-timed emphasis (audio energy) plus AI-suggested emphasis moments
        # (clip-local seconds) plus timeline punch-ins (source seconds), all
        # merged into one clip-local emphasis timeline.
        emphasis_times = [
            round(t - clip.start_seconds, 3)
            for t in beats
            if clip.start_seconds < t < clip.end_seconds
        ]
        plan_data = clip.editing_plan_json or {}
        for t in plan_data.get("emphasis_times", []) or []:
            try:
                value = round(float(t), 3)
            except (TypeError, ValueError):
                continue
            if 0.0 < value < clip.duration_seconds:
                emphasis_times.append(value)
        for pin in punch_ins or []:
            try:
                value = round(float(pin["time"]) - clip.start_seconds, 3)
            except (TypeError, ValueError, KeyError):
                continue
            if 0.0 < value < clip.duration_seconds:
                emphasis_times.append(value)
        emphasis_times = sorted(set(emphasis_times))

        emoji_triggers = _sanitize_render_emoji_triggers(
            plan_data.get("emoji_triggers", []), clip.duration_seconds
        )
        cta_text = plan_data.get("cta_text")
        lower_third_text = plan_data.get("hook_text") or clip.title

        music_path: str | None = None
        if style.audio.music_enabled:
            bpm = await self._video_bpm(clip.video_id)
            music_path = str(
                await asyncio.to_thread(
                    generate_music_bed,
                    scratch_dir / "music_bed.wav",
                    clip.duration_seconds,
                    bpm=bpm,
                )
            )

        sfx_triggers: list[dict] | None = None
        if style.audio.sfx_enabled and emphasis_times:
            sfx_path = str(
                await asyncio.to_thread(
                    generate_sfx, scratch_dir / f"{sfx_kind}.wav", sfx_kind
                )
            )
            sfx_triggers = [
                {"path": sfx_path, "time": t, "volume_db": 0.0}
                for t in emphasis_times
            ]

        composite = CompositeRenderer(
            caption_renderer=self._renderer,
            framing_analyzer=self._framing,
            style=style,
        )
        caption_ass, caption_frames_dir = self._build_captions(
            words,
            clip,
            canvas,
            preset,
            style,
            scratch_dir,
            faces=faces,
            theme=caption_theme,
            highlight_words=caption_highlight_words,
        )
        overlays_rasterized = await self._rasterize_overlays(
            caption_frames_dir,
            emoji_triggers,
            lower_third_text,
            cta_text,
            style,
            canvas,
            clip.duration_seconds,
        )
        await composite.render_clip(
            source_path=source_path,
            output_path=rendered_path,
            clip_start=clip.start_seconds,
            clip_end=clip.end_seconds,
            transcript_words=words,
            canvas=canvas,
            preset=preset,
            framing=framing_plan,
            emphasis_times=emphasis_times,
            music_path=music_path,
            sfx_triggers=sfx_triggers,
            lower_third_text=None if overlays_rasterized else lower_third_text,
            cta_text=None if overlays_rasterized else cta_text,
            emoji_triggers=[] if overlays_rasterized else emoji_triggers,
            caption_ass=caption_ass,
            caption_frames_dir=caption_frames_dir,
            caption_fps=CAPTION_RENDER_FPS,
        )

        await self._store_and_finalize(clip, rendered_path, scratch_dir)

    async def _render_clip_plugin(
        self,
        clip: Clip,
        source_path: Path,
        words: list[dict],
        canvas: tuple[int, int],
        scratch_dir: Path,
        style: RenderStyle,
        preset: str,
        beats: list[float],
        sfx_kind: str = "whoosh",
        punch_ins: list[dict[str, Any]] | None = None,
        blueprint: dict[str, Any] | None = None,
        caption_theme: str | None = None,
        caption_highlight_words: tuple[str, ...] = (),
    ) -> None:
        """Plugin-driven render when the blueprint has timeline events.

        Falls back to the legacy `_render_clip` when there are no in-window
        events, so videos without a blueprint keep today's exact behavior.
        """
        events_by_track = compile_clip_events(blueprint, clip.start_seconds, clip.end_seconds)
        if not events_by_track:
            await self._render_clip(
                clip,
                source_path,
                words,
                canvas,
                scratch_dir,
                style,
                preset,
                beats,
                sfx_kind,
                punch_ins,
                caption_theme=caption_theme,
                caption_highlight_words=caption_highlight_words,
            )
            return

        rendered_path = scratch_dir / f"rendered_{clip.id}.mp4"
        framing_plan = await self._framing_plan(source_path, canvas)

        faces: tuple[tuple[float, float, float, float], ...] = ()
        if self._caption_engine != "legacy":
            faces = tuple(
                await asyncio.to_thread(
                    detect_face_boxes, str(source_path), canvas, framing_plan
                )
            )

        emphasis_times = await self._emphasis_times(clip, beats, punch_ins)

        ctx = RenderContext(
            clip=clip,
            canvas=canvas,
            clip_start=clip.start_seconds,
            clip_end=clip.end_seconds,
            clip_duration=clip.duration_seconds,
            preset=preset,
            style=style,
            words=words,
            framing=framing_plan,
            faces=faces,
            emphasis_times=emphasis_times,
        )
        batch = await self._pipeline.render(ctx, events_by_track)

        caption_style = style
        if ctx.caption_updates:
            caption_style = replace(
                style, caption=replace(style.caption, **ctx.caption_updates)
            )
        theme = ctx.caption_theme or caption_theme
        highlight_words = (
            tuple(ctx.caption_highlight_words)
            if ctx.caption_highlight_words
            else caption_highlight_words
        )
        caption_ass, caption_frames_dir = self._build_captions(
            words,
            clip,
            canvas,
            preset,
            caption_style,
            scratch_dir,
            faces=faces,
            theme=theme,
            highlight_words=highlight_words,
        )

        # Plugin events win over the preset gates: an event-driven music path,
        # SFX hits, emoji / lower-third / CTA overlays are honored even when
        # the baseline style disables them. Otherwise fall back to the legacy
        # generated bed.
        audio_updates: dict[str, Any] = {}
        if ctx.music_path:
            audio_updates["music_enabled"] = True
        sfx_triggers = list(batch.sfx_triggers)
        if sfx_triggers:
            audio_updates["sfx_enabled"] = True

        overlay_updates: dict[str, Any] = {}
        if ctx.overlay_events:
            overlay_updates["emojis_enabled"] = True
        if ctx.lower_third_text:
            overlay_updates["lower_thirds_enabled"] = True
        if ctx.cta_text:
            overlay_updates["cta_enabled"] = True

        composite_style = style
        if audio_updates:
            composite_style = replace(
                style, audio=replace(style.audio, **audio_updates)
            )
        if overlay_updates:
            composite_style = replace(
                composite_style,
                overlays=replace(composite_style.overlays, **overlay_updates),
            )

        overlays_rasterized = await self._rasterize_overlays(
            caption_frames_dir,
            list(batch.overlay_events),
            batch.lower_third_text,
            batch.cta_text,
            composite_style,
            canvas,
            clip.duration_seconds,
        )
        if overlays_rasterized:
            batch = replace(
                batch, overlay_events=(), lower_third_text=None, cta_text=None
            )

        music_path = batch.music_path
        if music_path is None and style.audio.music_enabled:
            bpm = await self._video_bpm(clip.video_id)
            music_path = str(
                await asyncio.to_thread(
                    generate_music_bed,
                    scratch_dir / "music_bed.wav",
                    clip.duration_seconds,
                    bpm=bpm,
                )
            )

        if sfx_triggers:
            sfx_triggers = await self._materialize_sfx(
                sfx_triggers, sfx_kind, scratch_dir
            )
        batch = replace(
            batch,
            music_path=music_path,
            sfx_triggers=tuple(sfx_triggers),
        )

        composite = CompositeRenderer(
            caption_renderer=self._renderer,
            framing_analyzer=self._framing,
            style=composite_style,
        )
        await composite.render_clip_batch(
            source_path=source_path,
            output_path=rendered_path,
            clip_start=clip.start_seconds,
            clip_end=clip.end_seconds,
            canvas=canvas,
            batch=batch,
            transcript_words=words,
            preset=preset,
            framing=framing_plan,
            caption_ass=caption_ass,
            caption_frames_dir=caption_frames_dir,
            caption_fps=CAPTION_RENDER_FPS,
        )

        await self._store_and_finalize(clip, rendered_path, scratch_dir)

    async def _emphasis_times(
        self,
        clip: Clip,
        beats: list[float],
        punch_ins: list[dict[str, Any]] | None,
    ) -> list[float]:
        """Clip-local emphasis timeline from beats + plan + timeline punch-ins."""
        emphasis = [
            round(t - clip.start_seconds, 3)
            for t in beats
            if clip.start_seconds < t < clip.end_seconds
        ]
        plan_data = clip.editing_plan_json or {}
        for t in plan_data.get("emphasis_times", []) or []:
            try:
                value = round(float(t), 3)
            except (TypeError, ValueError):
                continue
            if 0.0 < value < clip.duration_seconds:
                emphasis.append(value)
        for pin in punch_ins or []:
            try:
                value = round(float(pin["time"]) - clip.start_seconds, 3)
            except (TypeError, ValueError, KeyError):
                continue
            if 0.0 < value < clip.duration_seconds:
                emphasis.append(value)
        return sorted(set(emphasis))

    async def _materialize_sfx(
        self,
        sfx_triggers: list[dict[str, Any]],
        default_kind: str,
        scratch_dir: Path,
    ) -> list[dict[str, Any]]:
        """Ensure every SFX trigger has a real audio file path.

        Generated files are cached per kind so multiple triggers on the same
        clip reuse one wav. Triggers that specify a path keep it.
        """
        generated: dict[str, str] = {}
        materialized: list[dict[str, Any]] = []
        for trigger in sfx_triggers:
            if trigger.get("path"):
                materialized.append(trigger)
                continue
            kind = str(trigger.get("kind") or default_kind)
            if kind not in generated:
                generated[kind] = str(
                    await asyncio.to_thread(
                        generate_sfx, scratch_dir / f"{kind}.wav", kind
                    )
                )
            materialized.append(
                {
                    "path": generated[kind],
                    "time": trigger.get("time", 0.0),
                    "volume_db": trigger.get("volume_db", 0.0),
                }
            )
        return materialized

    async def _store_and_finalize(
        self, clip: Clip, rendered_path: Path, scratch_dir: Path
    ) -> None:
        storage_key = f"clips/{clip.id}/rendered_{clip.id}.mp4"
        with open(rendered_path, "rb") as f:
            await self._storage.put(storage_key, f, "video/mp4")

        thumb_key = f"clips/{clip.id}/thumb_{clip.id}.jpg"
        thumb_path = scratch_dir / f"thumb_{clip.id}.jpg"
        try:
            await self._thumbnails.generate(
                source_path=str(rendered_path),
                timestamp_seconds=clip.duration_seconds / 2,
                output_path=str(thumb_path),
            )
            with open(thumb_path, "rb") as f:
                await self._storage.put(thumb_key, f, "image/jpeg")
        except Exception:
            logger.warning("render_thumbnail_failed", clip_id=str(clip.id))
            thumb_key = None

        updated = await self._clips.update_render(
            clip.id, storage_key, thumbnail_storage_key=thumb_key
        )
        if updated is None:
            logger.warning("render_clip_missing_on_update", clip_id=str(clip.id))
        logger.info(
            "clip_rendered",
            clip_id=str(clip.id),
            storage_key=storage_key,
        )

    async def _video_bpm(self, video_id: uuid.UUID) -> float | None:
        video = await self._videos.get_by_id(video_id)
        if video is None or not video.metadata_json:
            return None
        audio = video.metadata_json.get("audio") or {}
        bpm = audio.get("bpm")
        try:
            return float(bpm) if bpm else None
        except (TypeError, ValueError):
            return None

    async def _framing_plan(
        self,
        source_path: Path,
        canvas: tuple[int, int],
    ) -> FramingPlan | None:
        """Subject-tracking crop for portrait canvases, or None to keep the
        plain center crop (landscape canvas, no analyzer, untrackable source)."""
        if self._framing is None or canvas[0] / canvas[1] > 1.0:
            return None
        try:
            probe = await asyncio.to_thread(run_ffprobe, source_path)
            meta = build_metadata(probe)
            video = meta.get("video_stream") or {}
            width, height = video.get("width"), video.get("height")
        except Exception as exc:
            logger.warning("framing_probe_failed", error=str(exc)[:200])
            return None
        if not width or not height:
            return None
        source_w, source_h = int(width), int(height)
        window = crop_window_for_target(source_w, source_h, canvas[0] / canvas[1])
        if window is None:
            return None
        try:
            points = await asyncio.to_thread(
                self._framing.analyze, str(source_path), source_w, source_h
            )
        except Exception:
            logger.exception("framing_analyze_failed", source=str(source_path))
            return None
        fitted = fit_points(points, window, source_w, source_h)
        if not fitted:
            return None
        x_expr, y_expr = build_crop_expressions(fitted, window, source_w, source_h)
        return FramingPlan(window=window, x_expression=x_expr, y_expression=y_expr)

    async def _transcript_words(self, video_id: uuid.UUID) -> list[dict]:
        transcript = await self._transcripts.get_by_video_id(video_id)
        return list(transcript.words) if transcript else []

    def _build_captions(
        self,
        words: list[dict[str, Any]],
        clip: Clip,
        canvas: tuple[int, int],
        preset: str,
        style: RenderStyle,
        scratch_dir: Path,
        faces: tuple[tuple[float, float, float, float], ...] = (),
        theme: str | None = None,
        highlight_words: tuple[str, ...] = (),
    ) -> tuple[str | None, Path | None]:
        """Build the clip's captions with the configured engine.

        ``faces`` are output-canvas face boxes (left, top, right, bottom)
        the MotionCaption placement engine avoids; ``theme`` overrides the
        preset theme mapping; ``highlight_words`` become karaoke emphasis.

        Returns ``(caption_ass, caption_frames_dir)``; both may be None,
        in which case the composite renderer falls back to its legacy
        caption track so the burn-in never silently disappears.
        """
        if self._caption_engine == "frames":
            frames_dir = scratch_dir / f"captions_{clip.id}"
            return None, build_motion_caption_frames(
                words,
                clip.start_seconds,
                clip.end_seconds,
                preset=preset,
                canvas=canvas,
                accent_color=style.caption.active_color,
                muted_color=style.caption.muted_color,
                animation=style.caption.animation,
                out_dir=frames_dir,
                fps=CAPTION_RENDER_FPS,
                faces=faces,
                face_margin=style.caption.face_margin,
                theme=theme,
                highlight_words=highlight_words,
            )
        if self._caption_engine == "ass":
            return (
                build_motion_caption_ass(
                    words,
                    clip.start_seconds,
                    clip.end_seconds,
                    preset=preset,
                    canvas=canvas,
                    accent_color=style.caption.active_color,
                    muted_color=style.caption.muted_color,
                    animation=style.caption.animation,
                    faces=faces,
                    face_margin=style.caption.face_margin,
                    theme=theme,
                    highlight_words=highlight_words,
                ),
                None,
            )
        return None, None

    async def _rasterize_overlays(
        self,
        caption_frames_dir: Path | None,
        emoji_triggers: list[dict[str, Any]] | None,
        lower_third_text: str | None,
        cta_text: str | None,
        style: RenderStyle,
        canvas: tuple[int, int],
        clip_duration: float,
    ) -> bool:
        """Draw overlays into the caption frames (frames engine only).

        Returns True when overlays were rasterized so the caller can skip the
        libass burn-in for them.
        """
        if caption_frames_dir is None:
            return False
        plan = OverlayEngine(style.overlays).build_plan(
            clip_duration,
            emoji_triggers=emoji_triggers,
            lower_third_text=lower_third_text,
            cta_text=cta_text,
        )
        if not (plan.emojis or plan.lower_thirds or plan.ctas):
            return False
        await asyncio.to_thread(
            rasterize_overlays_into_frames,
            caption_frames_dir,
            plan,
            canvas,
            fps=CAPTION_RENDER_FPS,
        )
        return True

    async def _notify_rendered(
        self, video_id: uuid.UUID, rendered: int, skipped: int
    ) -> None:
        try:
            await self._notifier.publish(
                {
                    "video_id": str(video_id),
                    "status": "ready",
                    "stage": "render",
                    "message": f"Rendered {rendered} clips with captions",
                }
            )
        except Exception:
            logger.warning(
                "status publish failed; continuing", video_id=str(video_id)
            )


def _sfx_kind(overrides: dict | None) -> str:
    """Pick the synth SFX kind from the plan's directives (default whoosh)."""
    if not isinstance(overrides, dict):
        return "whoosh"
    types = overrides.get("sfx_types") or []
    for kind in types:
        if isinstance(kind, str) and kind.lower() in ("whoosh", "boom"):
            return kind.lower()
    return "whoosh"


def _sanitize_render_emoji_triggers(
    triggers: list, duration: float
) -> list[dict]:
    """Defensive pass over stored emoji triggers before they reach OverlayEngine."""
    result: list[dict] = []
    for trigger in triggers or []:
        if not isinstance(trigger, dict):
            continue
        emoji = trigger.get("emoji")
        if not emoji or not isinstance(emoji, str):
            continue
        try:
            value = float(trigger.get("time", 0.0))
        except (TypeError, ValueError):
            continue
        if not (0.0 <= value < duration):
            continue
        result.append({"emoji": emoji[:8], "time": round(value, 3)})
    return result
