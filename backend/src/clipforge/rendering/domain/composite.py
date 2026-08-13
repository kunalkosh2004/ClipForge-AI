"""Composite rendering engine combining captions, zoom, overlays, and audio.

This is the real render path used by the pipeline: it normalizes the source
clip onto the target canvas, applies beat-timed punch/emphasis zooms, burns
word-by-word captions plus overlay events, and mixes a music bed and SFX
tuned to the clip's beat-drop timestamps.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from clipforge.common import logging as logging_mod
from clipforge.processing.infrastructure.ffprobe import (
    build_metadata,
    run_ffprobe,
)
from clipforge.rendering.domain.audio import AudioEngine, AudioPlan
from clipforge.rendering.domain.batch import FilterBatch
from clipforge.rendering.domain.captions import ass_header, build_caption_ass
from clipforge.rendering.domain.framing import FramingPlan
from clipforge.rendering.domain.overlays import OverlayEngine
from clipforge.rendering.domain.ports import CaptionRenderer, FramingAnalyzer
from clipforge.rendering.domain.styles import RenderStyle
from clipforge.rendering.domain.zoom import ZoomEngine, ZoomPlan

logger = logging_mod.get_logger(__name__)


class CompositeRenderer:
    def __init__(
        self,
        caption_renderer: CaptionRenderer,
        framing_analyzer: FramingAnalyzer | None,
        style: RenderStyle,
    ):
        self._caption_renderer = caption_renderer
        self._framing_analyzer = framing_analyzer
        self.style = style
        self.zoom_engine = ZoomEngine(style.zoom)
        self.overlay_engine = OverlayEngine(style.overlays)
        self.audio_engine = AudioEngine(style.audio)

    async def render_clip(
        self,
        source_path: Path,
        output_path: Path,
        clip_start: float,
        clip_end: float,
        transcript_words: list[dict[str, Any]],
        canvas: tuple[int, int],
        preset: str = "default",
        framing: FramingPlan | None = None,
        emphasis_times: list[float] | None = None,
        music_path: str | None = None,
        sfx_triggers: list[dict[str, Any]] | None = None,
        lower_third_text: str | None = None,
        cta_text: str | None = None,
        emoji_triggers: list[dict[str, Any]] | None = None,
        caption_ass: str | None = None,
        caption_frames_dir: Path | None = None,
        caption_fps: int = 30,
    ) -> None:
        clip_duration = max(clip_end - clip_start, 0.1)

        zoom_plan = self.zoom_engine.build_zoom_plan(
            clip_duration, emphasis_times, keyword_times=emphasis_times
        )
        overlay_plan = self.overlay_engine.build_plan(
            clip_duration,
            emoji_triggers=emoji_triggers,
            lower_third_text=lower_third_text,
            cta_text=cta_text,
        )
        audio_plan = self.audio_engine.build_plan(
            clip_duration, music_path=music_path, sfx_triggers=sfx_triggers
        )

        # A pre-built caption ASS (MotionCaption engine) wins; otherwise fall
        # back to the legacy word-by-word builder so the track always exists.
        # Frame-sequence captions composite as pixels, so they need no word
        # ASS at all — only the overlay events (emoji/CTA/lower-third) burn.
        overlay_events = overlay_plan.to_ass_events(canvas[0], canvas[1])
        ass = caption_ass
        if ass is None and caption_frames_dir is None:
            ass = build_caption_ass(
                transcript_words,
                clip_start,
                clip_end,
                preset,
                canvas=canvas,
                accent_color=self.style.caption.active_color,
            )
        if ass and overlay_events:
            ass = ass.rstrip() + "\n" + "\n".join(overlay_events) + "\n"
        elif overlay_events:
            ass = ass_header(canvas) + "\n".join(overlay_events) + "\n"

        has_audio = await self._source_has_audio(source_path)
        video_chain = self._build_video_chain(canvas, framing, zoom_plan)
        await self._render_with_filter(
            source_path,
            output_path,
            video_chain=video_chain,
            ass=ass,
            audio_plan=audio_plan,
            has_audio=has_audio,
            clip_duration=clip_duration,
            caption_frames_dir=caption_frames_dir,
            caption_fps=caption_fps,
        )

    async def _source_has_audio(self, source_path: Path) -> bool:
        try:
            probe = await asyncio.to_thread(run_ffprobe, source_path)
            meta = build_metadata(probe)
            return bool((meta.get("audio_stream") or {}).get("codec"))
        except Exception:
            return True  # assume audio; ffmpeg will error out if truly absent

    async def render_clip_batch(
        self,
        source_path: Path,
        output_path: Path,
        clip_start: float,
        clip_end: float,
        canvas: tuple[int, int],
        batch: FilterBatch,
        transcript_words: list[dict[str, Any]],
        preset: str = "default",
        framing: FramingPlan | None = None,
        caption_ass: str | None = None,
        caption_frames_dir: Path | None = None,
        caption_fps: int = 30,
    ) -> None:
        """Render a clip from a plugin-produced ``FilterBatch``.

        The batch carries the blueprint-driven operations (grade/zoom filters,
        overlay events, music/SFX triggers); the base framing/scale chain and
        the caption burn-in are shared with ``render_clip``. The ``transition``
        field is the M6 final assembler's job and is never applied here.
        """
        clip_duration = max(clip_end - clip_start, 0.1)

        overlay_plan = self.overlay_engine.build_plan(
            clip_duration,
            emoji_triggers=list(batch.overlay_events),
            lower_third_text=batch.lower_third_text,
            cta_text=batch.cta_text,
        )
        audio_plan = self.audio_engine.build_plan(
            clip_duration,
            music_path=batch.music_path,
            sfx_triggers=list(batch.sfx_triggers),
            volume_db=batch.music_volume_db,
        )

        overlay_events = overlay_plan.to_ass_events(canvas[0], canvas[1])
        ass = caption_ass
        if ass is None and caption_frames_dir is None:
            ass = build_caption_ass(
                transcript_words,
                clip_start,
                clip_end,
                preset,
                canvas=canvas,
                accent_color=self.style.caption.active_color,
            )
        if ass and overlay_events:
            ass = ass.rstrip() + "\n" + "\n".join(overlay_events) + "\n"
        elif overlay_events:
            ass = ass_header(canvas) + "\n".join(overlay_events) + "\n"

        has_audio = await self._source_has_audio(source_path)
        video_chain = self._build_video_chain(
            canvas, framing, extra_filters=batch.video_filters
        )
        await self._render_with_filter(
            source_path,
            output_path,
            video_chain=video_chain,
            ass=ass,
            audio_plan=audio_plan,
            has_audio=has_audio,
            clip_duration=clip_duration,
            caption_frames_dir=caption_frames_dir,
            caption_fps=caption_fps,
        )

    def _build_video_chain(
        self,
        canvas: tuple[int, int],
        framing: FramingPlan | None,
        zoom_plan: ZoomPlan | None = None,
        extra_filters: tuple[str, ...] = (),
    ) -> list[str]:
        width, height = canvas
        chain: list[str] = []

        if framing is not None:
            chain.append(
                f"crop={framing.window.width}:{framing.window.height}:"
                f"'{framing.x_expression}':'{framing.y_expression}',"
                f"scale={width}:{height}"
            )
        elif width / height < 1.0:
            chain.append(
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}"
            )
        else:
            chain.append(
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
            )

        if self.style.background.type == "blur":
            chain.append(
                f"gblur=sigma={self.style.background.blur_strength},"
                f"scale={width}:{height}"
            )

        if zoom_plan is not None:
            zoom_expr = zoom_plan.to_filter_expr(width, height)
            if zoom_expr != f"scale={width}:{height}":
                chain.append(zoom_expr)

        # Plugin-driven filters (color grade, camera zoom keyframes) land
        # after the base scale and before the caption burn-in.
        chain.extend(extra_filters)

        chain.append("setsar=1")
        return chain

    async def _render_with_filter(
        self,
        source_path: Path,
        output_path: Path,
        video_chain: list[str],
        ass: str | None,
        audio_plan: AudioPlan,
        has_audio: bool,
        clip_duration: float,
        caption_frames_dir: Path | None = None,
        caption_fps: int = 30,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ass_path: Path | None = None
            if ass:
                ass_path = tmp / "captions.ass"
                ass_path.write_text(ass, encoding="utf-8")

            video_filters = list(video_chain)
            if ass_path is not None:
                video_filters.append(f"ass={_escape_filter_path(str(ass_path))}")

            parts = [f"[0:v]{','.join(video_filters)}[base]"]

            inputs: list[str] = ["-y", "-i", str(source_path)]
            audio_labels: list[str] = []
            idx = 1

            if caption_frames_dir is not None:
                # MotionCaption frame sequence: 000000.png, 000001.png, …
                # composited over the whole clip at the caption fps.
                inputs.extend(
                    [
                        "-framerate",
                        str(caption_fps),
                        "-start_number",
                        "0",
                        "-i",
                        str(caption_frames_dir / "%06d.png"),
                    ]
                )
                parts.append(f"[{idx}:v]format=rgba[caps]")
                parts.append(
                    "[base][caps]overlay=0:0:shortest=1:format=auto[v]"
                )
                idx += 1
            else:
                parts.append("[base]null[v]")

            if has_audio:
                parts.append("[0:a]anull[src_a]")
                audio_labels.append("[src_a]")

            if audio_plan.music:
                inputs.extend(["-i", audio_plan.music.path])
                vol = 10 ** (audio_plan.music.volume_db / 20)
                fade_out = audio_plan.music.fade_out
                st = max(clip_duration - fade_out, 0.0)
                parts.append(
                    f"[{idx}:a]volume={vol},"
                    f"afade=t=in:st=0:d={audio_plan.music.fade_in},"
                    f"afade=t=out:st={st}:d={fade_out}[music]"
                )
                audio_labels.append("[music]")
                idx += 1

            for sfx in audio_plan.sfx:
                inputs.extend(["-i", sfx.path])
                vol = 10 ** (sfx.volume_db / 20)
                delay_ms = int(sfx.time * 1000)
                parts.append(
                    f"[{idx}:a]volume={vol},"
                    f"adelay={delay_ms}|{delay_ms}[sfx{idx}]"
                )
                audio_labels.append(f"[sfx{idx}]")
                idx += 1

            cmd = ["ffmpeg", *inputs]
            if audio_labels:
                parts.append(
                    "".join(audio_labels)
                    + f"amix=inputs={len(audio_labels)}:duration=first:dropout_transition=3[aout]"
                )
                cmd.extend(["-filter_complex", ";".join(parts)])
                cmd.extend(["-map", "[v]", "-map", "[aout]"])
            else:
                cmd.extend(["-filter_complex", ";".join(parts)])
                cmd.extend(["-map", "[v]"])

            cmd.extend(["-t", f"{clip_duration:.3f}"])
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_path),
            ])

            logger.info(
                "composite_render",
                source=str(source_path),
                output=str(output_path),
                has_audio=has_audio,
                music=bool(audio_plan.music),
                sfx=len(audio_plan.sfx),
                overlays=bool(ass and "Dialogue" in ass),
                caption_frames=bool(caption_frames_dir),
            )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                error_msg = (stderr or b"").decode(errors="replace")
                raise RuntimeError(
                    f"Composite render failed: {error_msg}\nCMD: {' '.join(cmd)}"
                )

            logger.info("composite_render_complete", output=str(output_path))


def _escape_filter_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")
