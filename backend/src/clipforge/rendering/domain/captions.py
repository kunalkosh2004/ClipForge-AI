from dataclasses import dataclass
from typing import Any

from clipforge.common import logging as logging_mod

_ASS_COLORS = {
    "active": "FFFFFF",
    "muted": "9E9E9E",
    "outline": "000000",
    "storytelling": "FFD700",
    "tutorial": "4DD0E1",
    "reaction": "FFEB3B",
    "commentary": "FF9800",
    "motivational": "FFD54F",
    "podcast": "FFFFFF",
}

MAX_WORDS_PER_PHRASE = 6
MIN_PHRASE_GAP_SECONDS = 1.2
PHRASE_END_PUNCTUATION = frozenset(".?!…:;")

PORTRAIT_CANVAS = (1080, 1920)
FONT_SCALE = 0.0333
MARGIN_SCALE = 0.0833


@dataclass(frozen=True)
class CaptionStyle:
    font: str
    font_size: int
    active_color: str
    margin_v: int


def caption_style(
    preset: str, canvas_height: int = PORTRAIT_CANVAS[1], accent_color: str | None = None
) -> CaptionStyle:
    active = accent_color or _ASS_COLORS.get(preset, _ASS_COLORS["active"])
    return CaptionStyle(
        font="Noto Sans",
        font_size=max(int(round(canvas_height * FONT_SCALE)), 24),
        active_color=active,
        margin_v=max(int(round(canvas_height * MARGIN_SCALE)), 40),
    )


def build_caption_ass(
    words: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    preset: str,
    canvas: tuple[int, int] = PORTRAIT_CANVAS,
    accent_color: str | None = None,
) -> str | None:
    """Build an ASS subtitle document that renders word-by-word captions for a
    clip. Returns None when no words fall inside the clip window.

    The highlight sweeps through each phrase: previously spoken words render in
    a muted color while the word currently being spoken renders bold in the
    preset's accent color (`accent_color`, when given, overrides the preset).
    `words` are in source-video time; output timings are clip-local. `canvas`
    is the output resolution the ASS PlayRes must match so libass renders text
    without distortion.
    """
    clip_words = _words_in_window(words, clip_start, clip_end)
    # If no words in window, create a minimal placeholder so captions track exists
    if not clip_words:
        logger = logging_mod.get_logger(__name__)
        logger.warning(
            "no_transcript_words_in_clip_window",
            clip_start=clip_start,
            clip_end=clip_end,
            total_words=len(words),
        )
        # Return a minimal ASS with a single empty event to ensure track exists
        return _ass_header(caption_style(preset, canvas[1], accent_color), canvas) + "\n"

    style = caption_style(preset, canvas[1], accent_color)
    lines: list[str] = []
    for phrase in _chunk_phrases(clip_words):
        for index, word in enumerate(phrase):
            text = " ".join(
                _tagged_word(w["text"], w_start == index, style)
                for w_start, w in enumerate(phrase[: index + 1])
            )
            start = word["start"]
            end = phrase[index + 1]["start"] if index + 1 < len(phrase) else word["end"]
            if end <= start:
                end = start + 0.5
            lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Caption,,0,0,0,,{text}"
            )
    return _ass_header(style, canvas) + "\n".join(lines) + "\n"


def _words_in_window(
    words: list[dict[str, Any]], clip_start: float, clip_end: float
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for word in words:
        text = str(word.get("text", "")).strip()
        start = float(word.get("start", 0.0))
        end = float(word.get("end", start + 0.1))
        if not text:
            continue
        if end <= clip_start or start >= clip_end:
            continue
        local_start = max(start, clip_start) - clip_start
        local_end = min(end, clip_end) - clip_start
        if local_end - local_start <= 0.0:
            continue
        result.append({"text": text, "start": round(local_start, 3), "end": round(local_end, 3)})
    return result


def _chunk_phrases(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    phrases: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        current.append(word)
        ends_phrase = word["text"][-1] in PHRASE_END_PUNCTUATION
        too_long = len(current) >= MAX_WORDS_PER_PHRASE
        gap = (
            len(current) > 1 and word["start"] - current[-2]["end"] > MIN_PHRASE_GAP_SECONDS
        )
        if ends_phrase or too_long or gap:
            phrases.append(current)
            current = []
    if current:
        phrases.append(current)
    return phrases


def _tagged_word(text: str, active: bool, style: CaptionStyle) -> str:
    if active:
        color = style.active_color
        return f"{{\\c{_ass_color(color)}\\b1}}{text}{{\\b0}}"
    return f"{{\\c{_ass_color(_ASS_COLORS['muted'])}}}{text}"


def _ass_color(rgb_hex: str) -> str:
    r, g, b = rgb_hex[0:2], rgb_hex[2:4], rgb_hex[4:6]
    return f"&H00{b}{g}{r}&"


def _ass_time(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    centis = int(round(seconds * 100))
    hours, centis = divmod(centis, 360000)
    minutes, centis = divmod(centis, 6000)
    secs, centis = divmod(centis, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _ass_header(style: CaptionStyle, canvas: tuple[int, int]) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {canvas[0]}\n"
        f"PlayResY: {canvas[1]}\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        f"Style: Caption,{style.font},{style.font_size},"
        f"{_ass_color(style.active_color)},{_ass_color(_ASS_COLORS['active'])},"
        f"{_ass_color(_ASS_COLORS['outline'])},&H80000000,"
        "-1,0,0,0,100,100,0,0,1,2,1,2,60,60,"
        f"{style.margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def ass_header(canvas: tuple[int, int]) -> str:
    """Minimal ASS header with a generic Default style, for burn-in that only
    carries overlay events (emoji / CTA / lower-third)."""
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {canvas[0]}\n"
        f"PlayResY: {canvas[1]}\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1\n"
        f"{_overlay_style_lines()}"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _overlay_style_lines() -> str:
    """Style definitions every overlay event references (Emoji / LowerThird /
    CTA). Colors are overridden inline by each event; the style provides the
    baseline so libass does not fall back to the Default font."""
    return (
        "Style: Emoji,Apple Color Emoji,20,&H00FFFFFF,&H00FFFFFF,&H00000000,"
        "&H80000000,-1,0,0,0,100,100,0,0,1,0,0,5,10,10,10,1\n"
        "Style: LowerThird,Noto Sans,48,&H00FFFFFF,&H00FFFFFF,&H00FFFFFF,"
        "&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,10,10,10,1\n"
        "Style: CTA,Noto Sans,56,&H00FFFFFF,&H00FFFFFF,&H00FFFFFF,"
        "&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,10,1\n"
    )


def inject_overlay_styles(ass: str) -> str:
    """Ensure the Emoji / LowerThird / CTA styles exist in an ASS document.

    MotionCaption / legacy caption documents define only their own caption
    styles; overlay events appended afterwards reference the overlay styles,
    so those definitions are injected before the events section when missing.
    """
    if "Style: Emoji," in ass:
        return ass
    events_marker = "\n[Events]\n"
    if events_marker in ass:
        return ass.replace(events_marker, "\n" + _overlay_style_lines() + "\n[Events]\n", 1)
    return ass.rstrip() + "\n" + _overlay_style_lines()
