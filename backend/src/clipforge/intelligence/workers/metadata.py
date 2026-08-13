import asyncio
import base64
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from clipforge.common import logging as logging_mod
from clipforge.intelligence.workers.base import IntelligenceWorker
from clipforge.processing.infrastructure.ffprobe import (
    build_metadata,
    run_ffprobe,
    sha256_file,
)

logger = logging_mod.get_logger(__name__)


class MetadataWorker(IntelligenceWorker):
    """Checksum, container format, duration, fps, codec, resolution and a
    thumbnail. Reuses the platform's proven ffprobe helpers.
    """

    kind = "metadata"
    version = "metadata-v1"

    async def detect(
        self, source_path: Path | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        assert source_path is not None  # metadata always needs the source
        probe = await asyncio.to_thread(run_ffprobe, source_path)
        meta = build_metadata(probe)
        checksum = await asyncio.to_thread(sha256_file, source_path)
        size_bytes = source_path.stat().st_size
        video = meta["video_stream"]
        audio = meta["audio_stream"]
        fmt = meta["format"]
        thumbnail = await asyncio.to_thread(_extract_thumbnail, source_path)
        return {
            "checksum": checksum,
            "size_bytes": size_bytes,
            "duration_seconds": fmt.get("duration"),
            "format": fmt.get("name"),
            "fps": video.get("fps"),
            "codec": video.get("codec"),
            "width": video.get("width"),
            "height": video.get("height"),
            "profile": video.get("profile"),
            "audio_codec": audio.get("codec"),
            "sample_rate": audio.get("sample_rate"),
            "thumbnail_base64": thumbnail,
        }


def _extract_thumbnail(path: Path, seek_seconds: float = 0.5) -> str:
    """Extract a JPEG frame as base64. Best-effort: empty string on failure so
    the artifact is still produced (a frame at 0.5s may not exist for short
    clips)."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            out_path = Path(tmp.name)
        cmd = [
            "ffmpeg",
            "-v", "error",
            "-ss", f"{seek_seconds:.3f}",
            "-i", str(path),
            "-frames:v", "1",
            "-vf", "scale=480:-2",
            "-q:v", "5",
            "-y",
            str(out_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=60, check=False)
        if out_path.exists() and out_path.stat().st_size > 0:
            encoded = base64.b64encode(out_path.read_bytes()).decode("ascii")
            out_path.unlink(missing_ok=True)
            return encoded
        out_path.unlink(missing_ok=True)
        return ""
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("thumbnail_extraction_failed", error=str(exc)[:200])
        return ""
