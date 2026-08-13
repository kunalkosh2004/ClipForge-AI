"""FilterBatch: the typed output of the plugin render pipeline.

Plugins translate blueprint timeline events into render operations; the
pipeline collects those operations into a `FilterBatch` that the composite
encoder consumes. This container lives on the rendering side (not in the
`plugins` package) so the encoder never depends on plugin internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FilterBatch:
    """Render operations produced by one clip's plugin execution.

    ``video_filters`` are appended to the composited base chain (after the
    framing/scale crop, before the ASS/frames burn-in). ``overlay_events``,
    ``lower_third_text`` and ``cta_text`` feed the overlay engine;
    ``music_path`` / ``music_volume_db`` / ``sfx_triggers`` feed the audio
    engine. ``transition`` is recorded for the M6 final assembler and is
    never applied by a per-clip render.
    """

    video_filters: tuple[str, ...] = ()
    overlay_events: tuple[dict[str, Any], ...] = ()
    lower_third_text: str | None = None
    cta_text: str | None = None
    music_path: str | None = None
    music_volume_db: float | None = None
    sfx_triggers: tuple[dict[str, Any], ...] = ()
    transition: dict[str, Any] | None = None

    def is_empty(self) -> bool:
        return not (
            self.video_filters
            or self.overlay_events
            or self.lower_third_text
            or self.cta_text
            or self.music_path
            or self.sfx_triggers
            or self.transition
        )
