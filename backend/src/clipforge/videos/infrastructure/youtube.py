import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

YOUTUBE_URL_RE = re.compile(
    r"^https?://(?:www\.|m\.)?"
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/|live/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)

_VIDEO_SUFFIXES = (".mp4", ".m4a", ".webm", ".mkv", ".mov")


def extract_youtube_id(url: str) -> str | None:
    """Return the YouTube video id from a URL, or None if it is not a valid URL."""
    match = YOUTUBE_URL_RE.search(url.strip())
    return match.group(1) if match else None


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    title: str
    duration_seconds: float | None
    thumbnail_url: str | None


class YouTubeDownloader:
    def __init__(self, format: str = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b") -> None:
        self._format = format

    async def download(self, url: str, output_dir: Path) -> DownloadResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        return await asyncio.to_thread(self._download_sync, url, output_dir)

    def _download_sync(self, url: str, output_dir: Path) -> DownloadResult:
        opts = {
            "format": self._format,
            "outtmpl": str(output_dir / "video.%(ext)s"),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            raise RuntimeError(f"YouTube download failed: {str(exc)[:500]}") from exc
        if info is None:
            raise RuntimeError("YouTube downloader returned no video info")

        path = _find_largest_video(output_dir)
        if path is None:
            raise RuntimeError("downloaded video not found on disk")

        duration: float | None = None
        if info.get("duration"):
            try:
                duration = float(info["duration"])
            except (TypeError, ValueError):
                duration = None

        return DownloadResult(
            path=path,
            title=info.get("title") or "YouTube video",
            duration_seconds=duration,
            thumbnail_url=info.get("thumbnail"),
        )


def _find_largest_video(output_dir: Path) -> Path | None:
    candidates = [p for p in output_dir.iterdir() if p.is_file()]
    videos = [p for p in candidates if p.suffix.lower() in _VIDEO_SUFFIXES]
    if not videos:
        return None
    return max(videos, key=lambda p: p.stat().st_size)
