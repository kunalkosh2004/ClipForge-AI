"""Lyrics application service: orchestrates compilation behind the port."""

from __future__ import annotations

from clipforge.lyrics.domain.entities import CompiledLyrics, LyricsRequest
from clipforge.lyrics.domain.ports import LyricsCompiler
from clipforge.lyrics.infrastructure.motion_caption import MotionCaptionLyricsCompiler


class LyricsService:
    """High-level lyrics compiler facade.

    Validates the request and delegates to the configured ``LyricsCompiler``
    (the deterministic MotionCaption adapter by default). Keeping the port
    injection point means tests and future engines can swap the backend
    without touching the domain contract.
    """

    def __init__(self, compiler: LyricsCompiler | None = None) -> None:
        self._compiler = compiler or MotionCaptionLyricsCompiler()

    def compile_lyrics(self, request: LyricsRequest) -> CompiledLyrics:
        _validate_request(request)
        return self._compiler.compile(request)


def _validate_request(request: LyricsRequest) -> None:
    if request.canvas_width <= 0 or request.canvas_height <= 0:
        raise ValueError("canvas dimensions must be positive")
    if request.fps <= 0:
        raise ValueError("fps must be positive")
    for word in request.words:
        if not word.text.strip():
            raise ValueError("lyrics words must carry non-empty text")
        if word.end < word.start:
            raise ValueError(f"word ends before it starts: {word.text!r}")
