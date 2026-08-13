import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

from clipforge.common.ports import StorageProvider


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


async def download_to_tempfile(storage: StorageProvider, key: str) -> tuple[Path, str, int]:
    fd, tmp = tempfile.mkstemp(prefix="clipforge-", suffix=".upload")
    path = Path(tmp)
    try:
        handle: BinaryIO = await storage.get(key)
        with os.fdopen(fd, "wb") as dest, handle as src:
            while chunk := src.read(1024 * 1024):
                dest.write(chunk)
        return path, sha256_file(path), path.stat().st_size
    except Exception:
        path.unlink(missing_ok=True)
        raise


def run_ffprobe(path: Path, timeout: int = 60) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {(result.stderr or '').strip()[:500]}")
    return json.loads(result.stdout)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _frame_rate(stream: dict[str, Any]) -> float | None:
    raw = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
    if not raw or "/" not in raw:
        return None
    try:
        num, den = raw.split("/", 1)
        num, den = int(num), int(den)
        if den == 0:
            return None
        return round(num / den, 3)
    except (ValueError, TypeError):
        return None


def build_metadata(probe: dict[str, Any]) -> dict[str, Any]:
    streams = probe.get("streams", []) or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = probe.get("format", {}) or {}

    return {
        "format": {
            "name": fmt.get("format_name"),
            "duration": _to_float(fmt.get("duration")),
            "size": _to_int(fmt.get("size")),
        },
        "video_stream": {
            "codec": video.get("codec_name") if video else None,
            "width": video.get("width") if video else None,
            "height": video.get("height") if video else None,
            "fps": _frame_rate(video) if video else None,
            "profile": video.get("profile") if video else None,
        },
        "audio_stream": {
            "codec": audio.get("codec_name") if audio else None,
            "sample_rate": _to_int(audio.get("sample_rate")) if audio else None,
        },
    }
