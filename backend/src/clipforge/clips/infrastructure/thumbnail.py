import asyncio
import shutil

from clipforge.clips.domain.ports import ThumbnailGenerator
from clipforge.common import logging as logging_mod

logger = logging_mod.get_logger(__name__)


class FFmpegThumbnailGenerator(ThumbnailGenerator):
    async def generate(
        self,
        source_path: str,
        timestamp_seconds: float,
        output_path: str,
        width: int = 1080,
        height: int = 1920,
    ) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg binary not found on PATH")

        cmd = [
            ffmpeg,
            "-y",
            "-ss", f"{timestamp_seconds:.3f}",
            "-i", source_path,
            "-vframes", "1",
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "-q:v", "2",
            output_path,
        ]
        logger.info(
            "generating_thumbnail",
            source=source_path,
            timestamp=timestamp_seconds,
            output=output_path,
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg thumbnail failed (rc={proc.returncode}): "
                f"{stderr.decode()[-500:]}"
            )
