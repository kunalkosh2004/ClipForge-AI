"""Unit tests for blueprint-driven caption theming (M4b)."""

from clipforge.lyrics.application.blueprint import caption_theme_hint
from clipforge.lyrics.application.build import (
    clip_caption_request,
    emphasis_indices_for_words,
)

WORDS = [
    {"text": "This", "start": 0.0, "end": 0.5},
    {"text": "moment", "start": 0.5, "end": 1.0},
    {"text": "changes", "start": 1.0, "end": 1.5},
    {"text": "everything", "start": 1.5, "end": 2.0},
]


def _blueprint(style_name: str = "Cinematic Slow", **overrides) -> dict:
    subtitle_theme = {
        "colors": ["FFD700", "9E9E9E", "000000"],
        "animation": "highlight",
        "highlight_words": ["Moment", "EVERYTHING"],
    }
    subtitle_theme.update(overrides)
    return {
        "global_style": {
            "style_name": style_name,
            "subtitle_theme": subtitle_theme,
        }
    }


# ------------------------------------------------------------------ mapping


def test_maps_colors_animation_theme_and_highlights() -> None:
    hint = caption_theme_hint(_blueprint())
    assert hint.accent_color == "FFD700"
    assert hint.muted_color == "9E9E9E"
    assert hint.outline_color == "000000"
    assert hint.animation == "glow"  # "highlight" -> glow strategy
    assert hint.theme == "cinematic"  # style_name mentions cinematic
    assert hint.highlight_words == ("moment", "everything")


def test_word_animation_falls_back_to_animation() -> None:
    data = _blueprint(animation=None, word_animation="bounce")
    hint = caption_theme_hint(data)
    assert hint.animation == "bounce"


def test_malformed_blueprint_yields_none_hints() -> None:
    assert caption_theme_hint(None).accent_color is None
    hint = caption_theme_hint({"global_style": {"subtitle_theme": {}}})
    assert hint.accent_color is None
    assert hint.animation is None
    assert hint.theme is None
    assert hint.highlight_words == ()


def test_ignores_invalid_colors_and_animation() -> None:
    data = _blueprint(
        colors=["xyz", "#12", "FFF", "#123456"],
        animation="not-a-real-animation",
    )
    hint = caption_theme_hint(data)
    assert hint.accent_color == "123456"
    assert hint.muted_color is None
    assert hint.outline_color is None
    assert hint.animation is None


def test_theme_from_style_name_requires_known_theme() -> None:
    assert caption_theme_hint(_blueprint(style_name="Sporty hype")).theme == "sport"
    assert caption_theme_hint(_blueprint(style_name="Abstract vibe")).theme is None


# ------------------------------------------------------------------ emphasis


def test_emphasis_indices_match_windowed_words() -> None:
    assert emphasis_indices_for_words(WORDS, ("moment", "everything")) == (1, 3)
    assert emphasis_indices_for_words(WORDS, ()) == ()
    assert emphasis_indices_for_words(WORDS, ("missing",)) == ()


def test_clip_caption_request_marks_highlighted_words() -> None:
    request = clip_caption_request(
        WORDS,
        0.0,
        2.5,
        preset="podcast",
        canvas=(1920, 1080),
        accent_color="FFD700",
        muted_color="9E9E9E",
        animation="sweep",
        theme="cinematic",
        highlight_words=("moment", "EVERYTHING"),
    )
    assert request is not None
    assert request.theme == "cinematic"
    assert request.emphasis_indices == (1, 3)


def test_emphasis_indices_are_clip_local_after_windowing() -> None:
    # words outside the window shift the indices; "everything" is second
    # in-window (behind "changes") so it must be index 1, not 3.
    request = clip_caption_request(
        [{"text": "skip", "start": 9.0, "end": 9.5}, *WORDS],
        1.0,
        2.5,
        preset="podcast",
        canvas=(1920, 1080),
        accent_color="FFD700",
        muted_color="9E9E9E",
        animation="sweep",
        highlight_words=("everything",),
    )
    assert request is not None
    assert request.emphasis_indices == (1,)
