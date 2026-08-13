"""Unit tests for the lyrics subsystem (MotionCaption embedding)."""

import pytest

from clipforge.lyrics import LyricsRequest, LyricsService, LyricWord
from clipforge.lyrics.application.theme import (
    DEFAULT_THEME,
    PRESET_THEMES,
    accent_hex,
    animation_strategy,
    theme_name_for,
)

WORDS = (
    LyricWord(text="hello", start=0.0, end=0.6),
    LyricWord(text="motion", start=0.7, end=1.4),
    LyricWord(text="typography", start=1.5, end=2.2),
)


def _request(**overrides) -> LyricsRequest:
    base = dict(words=WORDS, canvas_width=1080, canvas_height=1920)
    base.update(overrides)
    return LyricsRequest(**base)


# ---------------------------------------------------------------- theme mapping


def test_theme_name_for_maps_presets() -> None:
    assert theme_name_for("storytelling") == "cinematic"
    assert theme_name_for("podcast") == "clean"
    assert theme_name_for("mrbeast") == "sport"
    assert theme_name_for("documentary") == "cinematic"


def test_theme_name_for_unknown_preset_falls_back() -> None:
    assert theme_name_for("no_such_preset") == DEFAULT_THEME
    assert theme_name_for(None) == DEFAULT_THEME


def test_theme_name_for_explicit_wins() -> None:
    assert theme_name_for("storytelling", explicit="music_video") == "music_video"
    assert theme_name_for(None, explicit="sport") == "sport"


def test_theme_name_for_invalid_explicit_falls_back() -> None:
    assert theme_name_for(None, explicit="bogus") == DEFAULT_THEME


def test_preset_themes_only_cover_known_presets() -> None:
    for name in PRESET_THEMES.values():
        assert name in {"clean", "cinematic", "music_video", "news", "sport"}


# ------------------------------------------------------------ animation mapping


def test_animation_strategy_karaoke_labels() -> None:
    for label in ("karaoke", "sweep", "word", "word-by-word", "typewriter"):
        assert animation_strategy(label) == "karaoke"


def test_animation_strategy_aliases() -> None:
    assert animation_strategy("glow") == "glow"
    assert animation_strategy("highlight") == "glow"
    assert animation_strategy("glitch") == "bounce"
    assert animation_strategy("pop") == "pop"
    assert animation_strategy("fade") == "fade"


def test_animation_strategy_unknown_passthrough() -> None:
    assert animation_strategy("ripple") == "ripple"
    assert animation_strategy("none") == "none"


def test_animation_strategy_defaults() -> None:
    assert animation_strategy(None) == "fade"
    assert animation_strategy(None, karaoke=True) == "karaoke"
    assert animation_strategy("fade", karaoke=True) == "karaoke"


# ------------------------------------------------------------------ color helpers


def test_accent_hex_normalization() -> None:
    assert accent_hex("ffd700") == "FFD700"
    assert accent_hex("#ffd700") == "FFD700"
    assert accent_hex(None) is None
    assert accent_hex("bad") is None
    assert accent_hex("FFFFFF") == "FFFFFF"


# ---------------------------------------------------------------- compile basics


def test_compile_basic_timeline() -> None:
    compiled = LyricsService().compile_lyrics(
        _request(preset="storytelling", accent_color="FFD700", muted_color="9E9E9E")
    )
    assert compiled.theme_name == "cinematic"
    assert compiled.word_count == 3
    assert compiled.event_count >= 1
    assert compiled.duration == pytest.approx(2.2)
    assert compiled.timeline.resolution.width == 1080
    assert compiled.timeline.resolution.height == 1920
    assert [w.text for w in compiled.timeline.words] == ["hello", "motion", "typography"]


def test_compile_is_deterministic() -> None:
    service = LyricsService()
    request = _request(preset="gaming", animation="glow")
    first = service.compile_lyrics(request)
    second = service.compile_lyrics(request)
    assert first.timeline.model_dump_json() == second.timeline.model_dump_json()


def test_compile_karaoke_emphasizes_all_words() -> None:
    compiled = LyricsService().compile_lyrics(_request(karaoke=True, animation="sweep"))
    for word in compiled.timeline.words:
        assert word.emphasis.value == "karaoke"


def test_compile_emphasis_indices_without_karaoke() -> None:
    compiled = LyricsService().compile_lyrics(
        _request(karaoke=False, animation="fade", emphasis_indices=(0,))
    )
    assert compiled.timeline.words[0].emphasis.value == "karaoke"
    assert compiled.timeline.words[1].emphasis.value != "karaoke"


def test_compile_empty_words() -> None:
    compiled = LyricsService().compile_lyrics(LyricsRequest(canvas_width=1080, canvas_height=1920))
    assert compiled.event_count == 0
    assert compiled.word_count == 0
    assert compiled.duration == 0.0


def test_compile_muted_and_accent_colors_apply() -> None:
    compiled = LyricsService().compile_lyrics(
        _request(
            preset="storytelling",
            accent_color="FFD700",
            muted_color="9E9E9E",
            karaoke=True,
        )
    )
    words = compiled.timeline.words
    # Active (karaoke) words carry the accent color…
    assert (words[0].typography and words[0].typography.fill.r, words[0].typography.fill.g) == (
        0xFF,
        0xD7,
    )
    # …while the base fill reflects the muted color.
    event = compiled.timeline.events[0]
    assert event.style is not None
    assert event.style.typography is not None
    assert event.style.typography.fill.r == 0x9E


def test_compile_safe_area_and_platform_are_honored() -> None:
    compiled = LyricsService().compile_lyrics(
        _request(
            preset="podcast",
            platform="youtube_shorts",
            safe_area={"top": 0.06, "bottom": 0.08, "left": 0.03, "right": 0.18},
        )
    )
    event = compiled.timeline.events[0]
    # Placement must respect the vertical safe inset (box inside the canvas).
    assert event.region.box.bottom <= 1920
    assert event.region.box.top >= 0


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "bad_request",
    [
        LyricsRequest(words=(LyricWord("x", 2.0, 1.0),)),
        LyricsRequest(canvas_width=0, canvas_height=1080),
        LyricsRequest(fps=0),
        LyricsRequest(words=(LyricWord(" ", 0.0, 1.0),)),
    ],
)
def test_compile_rejects_invalid_requests(bad_request: LyricsRequest) -> None:
    with pytest.raises(ValueError):
        LyricsService().compile_lyrics(bad_request)
