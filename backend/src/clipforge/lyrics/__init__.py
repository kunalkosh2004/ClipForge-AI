"""Lyrics subsystem: deterministic motion-typography captions.

This bounded context embeds the ``motion-caption`` engine and owns the
contract between ClipForge's transcript/clip data and the compiled
``SubtitleTimeline`` every caption backend (ASS, frames) consumes.
"""

from clipforge.lyrics.application.service import LyricsService
from clipforge.lyrics.domain.entities import CompiledLyrics, LyricsRequest, LyricWord
from clipforge.lyrics.domain.ports import LyricsCompiler
from clipforge.lyrics.infrastructure.motion_caption import MotionCaptionLyricsCompiler

__all__ = [
    "CompiledLyrics",
    "LyricsCompiler",
    "LyricsRequest",
    "LyricsService",
    "LyricWord",
    "MotionCaptionLyricsCompiler",
]
