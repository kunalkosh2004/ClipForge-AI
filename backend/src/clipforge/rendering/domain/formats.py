from clipforge.analysis.domain.presets import FORMAT_LANDSCAPE, FORMAT_PORTRAIT

PORTRAIT_CANVAS = (1080, 1920)
LANDSCAPE_CANVAS = (1920, 1080)

_CANVAS_BY_FORMAT: dict[str, tuple[int, int]] = {
    FORMAT_PORTRAIT: PORTRAIT_CANVAS,
    FORMAT_LANDSCAPE: LANDSCAPE_CANVAS,
}


def canvas_for_format(video_format: str) -> tuple[int, int] | None:
    """Output canvas for an aspect-ratio format. None means keep the source
    resolution unchanged (FORMAT_ORIGINAL)."""
    return _CANVAS_BY_FORMAT.get(video_format)
