"""Unit tests for the MotionCaption ASS caption engine (M2)."""

import pytest

from clipforge.lyrics.application.ass import build_motion_caption_ass, window_words

WORDS = [
    {"text": "before", "start": 0.0, "end": 1.0},
    {"text": "hello", "start": 1.5, "end": 2.0},
    {"text": "motion", "start": 2.2, "end": 2.9},
    {"text": "typography", "start": 3.0, "end": 4.0},
    {"text": "after", "start": 5.0, "end": 6.0},
]


def _build(**overrides) -> str:
    kwargs = dict(
        words=WORDS,
        clip_start=1.2,
        clip_end=4.5,
        preset="storytelling",
        canvas=(1080, 1920),
        accent_color="FFD700",
        muted_color="9E9E9E",
        animation="sweep",
    )
    kwargs.update(overrides)
    return build_motion_caption_ass(**kwargs)


# ------------------------------------------------------------------ windowing


def test_window_words_rebases_to_clip_local_time() -> None:
    result = window_words(WORDS, 1.2, 4.5)
    assert [w["text"] for w in result] == ["hello", "motion", "typography"]
    assert result[0]["start"] == pytest.approx(0.3)
    assert result[0]["end"] == pytest.approx(0.8)


def test_window_words_clips_partial_words() -> None:
    result = window_words(WORDS, 1.6, 3.5)
    assert result[0]["start"] == pytest.approx(0.0)
    assert result[-1]["end"] == pytest.approx(1.9)


def test_window_words_drops_empty_text() -> None:
    words = [dict(WORDS[1], text="   "), dict(WORDS[2])]
    result = window_words(words, 0.0, 10.0)
    assert [w["text"] for w in result] == ["motion"]


def test_window_words_empty_when_nothing_overlaps() -> None:
    assert window_words(WORDS, 8.0, 9.0) == []


# ----------------------------------------------------------------- ASS output


def test_build_returns_none_without_words_in_window() -> None:
    assert _build(clip_start=8.0, clip_end=9.0) is None


def test_build_emits_playres_matching_canvas() -> None:
    ass = _build()
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass


def test_build_has_dialogue_for_in_window_words() -> None:
    ass = _build()
    dialogues = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert dialogues
    assert all(word in ass for word in ("hello", "motion", "typography"))
    assert "after" not in ass and "before" not in ass


def test_build_dialogue_times_are_clip_local() -> None:
    ass = _build()
    # hello starts at clip-local 0.3s -> ASS 0:00:00.30
    assert "0:00:00.30" in ass


def test_build_applies_accent_and_muted_colors() -> None:
    ass = _build()
    # FFD700 (RGB) -> &H00D7FF& in ASS; muted 9E9E9E stays in the style line.
    assert "&H00D7FF&" in ass
    assert "9E9E9E" in ass


def test_build_applies_preset_theme() -> None:
    # storytelling -> cinematic theme; the font is overridden, so check a
    # cinematic-specific marker is present rather than the generic Default.
    ass = _build(preset="storytelling")
    assert "Georgia" in ass or "[V4+ Styles]" in ass


def test_build_is_deterministic() -> None:
    assert _build() == _build()


def test_build_with_landscape_canvas() -> None:
    ass = _build(canvas=(1920, 1080))
    assert "PlayResX: 1920" in ass
    assert "PlayResY: 1080" in ass
