from clipforge.rendering.domain.captions import (
    ass_header,
    inject_overlay_styles,
)
from clipforge.rendering.domain.overlays import (
    CTAOverlay,
    EmojiOverlay,
    LowerThird,
    OverlayPlan,
)


def test_ass_header_defines_overlay_styles() -> None:
    header = ass_header((1920, 1080))
    assert "Style: Emoji," in header
    assert "Style: LowerThird," in header
    assert "Style: CTA," in header


def test_inject_overlay_styles_adds_definitions_before_events() -> None:
    doc = (
        "[Script Info]\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Caption,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,"
        "&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,60,60,10,1\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    out = inject_overlay_styles(doc)
    assert out.count("Style: Emoji,") == 1
    assert out.count("Style: LowerThird,") == 1
    assert out.count("Style: CTA,") == 1
    assert out.index("Style: Emoji,") < out.index("[Events]")


def test_inject_overlay_styles_is_idempotent() -> None:
    doc = (
        "[Script Info]\n[V4+ Styles]\n"
        "Style: Emoji,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,"
        "&H80000000,-1,0,0,0,100,100,0,0,1,0,0,5,10,10,10,1\n"
        "[Events]\n"
    )
    assert inject_overlay_styles(doc) == doc


def test_overlay_events_use_fixed_style_names() -> None:
    plan = OverlayPlan(
        emojis=[EmojiOverlay(emoji="🔥", time=1.0)],
        lower_thirds=[LowerThird(text="hi", start_time=1, end_time=2)],
        ctas=[CTAOverlay(text="go", start_time=1, end_time=2)],
    )
    events = plan.to_ass_events(1920, 1080)
    assert any("Emoji,,0,0,0,," in e for e in events)
    assert any("LowerThird,,0,0,0,," in e for e in events)
    assert any("CTA,,0,0,0,," in e for e in events)
