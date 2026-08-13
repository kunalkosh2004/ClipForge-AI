import tempfile
from pathlib import Path

import pytest

from clipforge.rendering.application.frames_overlays import (
    rasterize_overlays_into_frames,
)
from clipforge.rendering.domain.overlays import (
    CTAOverlay,
    EmojiOverlay,
    LowerThird,
    OverlayPlan,
)

CANVAS = (1920, 1080)
FPS = 30


def _make_frames(duration: float) -> Path:
    from PIL import Image

    out = Path(tempfile.mkdtemp(prefix="frames-overlay-"))
    for i in range(int(duration * FPS)):
        Image.new("RGBA", CANVAS, (0, 0, 0, 0)).save(out / f"{i:06d}.png")
    return out


def test_empty_plan_is_noop() -> None:
    out = _make_frames(2.0)
    original = {p.name: p.read_bytes() for p in out.glob("*.png")}

    rasterize_overlays_into_frames(out, OverlayPlan(), CANVAS, fps=FPS)

    assert {p.name: p.read_bytes() for p in out.glob("*.png")} == original


def test_emoji_drawn_only_inside_its_window() -> None:
    out = _make_frames(3.0)
    plan = OverlayPlan(
        emojis=[
            EmojiOverlay(
                emoji="🔥", time=0.5, duration=1.0, x=0.1, y=0.1, scale=0.1
            )
        ]
    )

    rasterize_overlays_into_frames(out, plan, CANVAS, fps=FPS)

    from PIL import Image

    def non_transparent(frame_index: int) -> bool:
        img = Image.open(out / f"{frame_index:06d}.png").convert("RGBA")
        return img.getbbox() is not None

    assert not non_transparent(10)  # t=0.33 before the window
    assert non_transparent(20)  # t=0.67 inside
    assert non_transparent(30)  # t=1.0 boundary
    assert not non_transparent(60)  # t=2.0 after the window


def test_lower_third_and_cta_badges_drawn() -> None:
    out = _make_frames(3.0)
    plan = OverlayPlan(
        lower_thirds=[LowerThird(text="Meet Kuna", start_time=0.5, end_time=1.5)],
        ctas=[CTAOverlay(text="Follow", start_time=1.8, end_time=2.8)],
    )

    rasterize_overlays_into_frames(out, plan, CANVAS, fps=FPS)

    from PIL import Image

    lt = Image.open(out / "000030.png").convert("RGBA")  # t=1.0: LT active
    cta = Image.open(out / "000060.png").convert("RGBA")  # t=2.0: CTA active
    assert lt.getbbox() is not None
    assert cta.getbbox() is not None
    # badges sit in the lower band
    assert _bottom_band_pixels(lt) > 0
    assert _bottom_band_pixels(cta) > 0
    # between the two windows nothing is drawn
    gap = Image.open(out / "000048.png").convert("RGBA")  # t=1.6
    assert gap.getbbox() is None


def _bottom_band_pixels(img) -> int:
    px = img.load()
    count = 0
    for x in range(0, img.width, 4):
        for y in range(img.height * 3 // 4, img.height, 4):
            if px[x, y][3] > 0:
                count += 1
    return count
