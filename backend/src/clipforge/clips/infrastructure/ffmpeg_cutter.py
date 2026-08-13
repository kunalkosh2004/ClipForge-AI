import asyncio
from pathlib import Path

from clipforge.clips.domain.ports import VideoCutter
from clipforge.common import logging as logging_mod

logger = logging_mod.get_logger(__name__)


class FFmpegCutter(VideoCutter):
    async def cut_clip(
        self,
        source_path: str,
        start_seconds: float,
        end_seconds: float,
        output_path: str,
    ) -> None:
        duration = end_seconds - start_seconds
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(start_seconds),
            "-i", source_path,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]
        logger.info(
            "cutting_clip",
            source=source_path,
            start=start_seconds,
            end=end_seconds,
            output=output_path,
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            error_msg = (stderr or b"").decode(errors="replace")[:500]
            raise RuntimeError(f"FFmpeg clip extraction failed: {error_msg}")
        logger.info("clip_cut_complete", output=output_path, size=Path(output_path).stat().st_size)
