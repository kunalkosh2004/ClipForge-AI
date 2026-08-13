"""Ports for the lyrics compilation subsystem."""

from __future__ import annotations

from typing import Protocol

from clipforge.lyrics.domain.entities import CompiledLyrics, LyricsRequest


class LyricsCompiler(Protocol):
    """Compiles a ``LyricsRequest`` into a deterministic lyrics timeline."""

    def compile(self, request: LyricsRequest) -> CompiledLyrics: ...
