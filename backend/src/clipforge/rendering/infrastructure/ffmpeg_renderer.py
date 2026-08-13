import asyncio

from clipforge.common import logging as logging_mod
from clipforge.rendering.domain.framing import FramingPlan
from clipforge.rendering.domain.ports import CaptionRenderer

logger = logging_mod.get_logger(__name__)


class FFmpegCaptionRenderer(CaptionRenderer):
    async def render_captions(
        self,
        source_path: str,
        ass_path: str,
        output_path: str,
        width: int | None = None,
        height: int | None = None,
        framing: FramingPlan | None = None,
    ) -> None:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", source_path,
            "-vf", _video_filter(ass_path, width, height, framing),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]
        logger.info(
            "rendering_captions",
            source=source_path,
            subtitles=ass_path,
            output=output_path,
            width=width,
            height=height,
            framing=bool(framing),
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            error_msg = (stderr or b"").decode(errors="replace")[-500:]
            raise RuntimeError(f"FFmpeg caption render failed: {error_msg}")
        logger.info("caption_render_complete", output=output_path)


def _video_filter(
    ass_path: str,
    width: int | None,
    height: int | None,
    framing: FramingPlan | None = None,
) -> str:
    """Build the filtergraph: normalize the source onto the target canvas (if
    any), then burn the ASS.

    Portrait canvases cover-crop; when a framing plan is provided the crop
    window tracks the subject instead of being fixed to the center. Landscape
    canvases contain-pad. Without a canvas the source keeps its resolution.
    """
    chain: list[str] = []
    if width and height:
        if width / height < 1.0:
            if framing is not None:
                # expressions contain if() commas that would otherwise split
                # the filtergraph; single-quote them as option values
                chain.append(
                    f"crop={framing.window.width}:{framing.window.height}:"
                    f"'{framing.x_expression}':'{framing.y_expression}',"
                    f"scale={width}:{height}"
                )
            else:
                chain.append(
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height}"
                )
        else:
            chain.append(
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
            )
        chain.append("setsar=1")
    chain.append(f"ass={_escape_filter_path(ass_path)}")
    return ",".join(chain)


def _escape_filter_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")
