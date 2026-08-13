"""Overlay rasterization for the MotionCaption frames backend.

Emoji / lower-third / CTA overlays are drawn directly onto the RGBA caption
frames so the frames pipeline never needs libass to burn overlays. Emoji
glyphs are pulled from a color-emoji font as bitmaps (sbix / CBDT via
fontTools, or a plain PIL text render as a last resort) so the result is
deterministic across platforms.
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from clipforge.rendering.domain.overlays import OverlayPlan

__all__ = ["rasterize_overlays_into_frames"]

_EMOJI_FONT_CANDIDATES: tuple[str, ...] = (
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/opentype/noto/NotoColorEmoji.ttf",
    "C:/Windows/Fonts/seguiemj.ttf",
)

_TEXT_FONT_CANDIDATES: tuple[str, ...] = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)

_BADGE_MARGIN = 140
_BADGE_PAD_X = 24
_BADGE_PAD_Y = 14
_BADGE_RADIUS = 16


def rasterize_overlays_into_frames(
    out_dir: Path,
    plan: OverlayPlan,
    canvas: tuple[int, int],
    *,
    fps: int = 30,
    emoji_font_path: str | None = None,
    text_font_path: str | None = None,
) -> None:
    """Draw ``plan`` overlays onto the frames already written into ``out_dir``.

    Frames are ``000000.png``, ``000001.png``, … at ``fps`` frames per second;
    frame ``i`` covers clip-local time ``i / fps``. Only frames that intersect
    an active overlay are rewritten.
    """
    if not (plan.emojis or plan.lower_thirds or plan.ctas):
        return

    emoji_font = _load_emoji_font(emoji_font_path)
    text_fonts: dict[int, Any] = {}

    for frame_path in sorted(out_dir.glob("*.png")):
        index = _frame_index(frame_path)
        if index is None:
            continue
        t = index / fps
        layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        painted = False

        for emoji in plan.emojis:
            if emoji.time <= t < emoji.time + emoji.duration:
                glyph = emoji_font.render(emoji.emoji, int(canvas[1] * emoji.scale))
                if glyph is not None:
                    x = int(canvas[0] * emoji.x)
                    y = int(canvas[1] * emoji.y)
                    layer.alpha_composite(
                        glyph, (x - glyph.width // 2, y - glyph.height // 2)
                    )
                    painted = True

        for lt in plan.lower_thirds:
            if lt.start_time <= t <= lt.end_time:
                font = text_fonts.setdefault(
                    lt.font_size, _load_text_font(lt.font_size, text_font_path)
                )
                _draw_badge(
                    draw,
                    lt.text,
                    font,
                    _parse_rgba(lt.color),
                    _parse_rgba(lt.bg_color),
                    canvas,
                    lt.position,
                )
                painted = True

        for cta in plan.ctas:
            if cta.start_time <= t <= cta.end_time:
                font = text_fonts.setdefault(
                    cta.font_size, _load_text_font(cta.font_size, text_font_path)
                )
                _draw_badge(
                    draw,
                    cta.text,
                    font,
                    _parse_rgba(cta.color),
                    _parse_rgba(cta.bg_color),
                    canvas,
                    cta.position,
                )
                painted = True

        if painted:
            frame = Image.open(frame_path).convert("RGBA")
            frame.alpha_composite(layer)
            frame.save(frame_path)


def _frame_index(frame_path: Path) -> int | None:
    try:
        return int(frame_path.stem)
    except ValueError:
        return None


def _parse_rgba(hex_value: str) -> tuple[int, int, int, int]:
    value = hex_value.lstrip("#")
    if len(value) == 8:
        rgb, alpha = value[:6], value[6:8]
        r, g, b = _hex_byte(rgb[0:2]), _hex_byte(rgb[2:4]), _hex_byte(rgb[4:6])
        return (r, g, b, _hex_byte(alpha))
    r, g, b = _hex_byte(value[0:2]), _hex_byte(value[2:4]), _hex_byte(value[4:6])
    return (r, g, b, 255)


def _hex_byte(part: str) -> int:
    try:
        return int(part, 16)
    except ValueError:
        return 255


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: Any,
    color: tuple[int, int, int, int],
    bg_color: tuple[int, int, int, int],
    canvas: tuple[int, int],
    position: str,
) -> None:
    if font is None:
        return
    width, height = canvas
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, anchor="ma")
    box_w = (right - left) + 2 * _BADGE_PAD_X
    box_h = (bottom - top) + 2 * _BADGE_PAD_Y
    cx = width // 2
    if position == "top":
        box_top = _BADGE_MARGIN
    else:
        box_top = height - _BADGE_MARGIN - box_h
    box = (cx - box_w // 2, box_top, cx + box_w // 2, box_top + box_h)
    draw.rounded_rectangle(
        (box[0] + 4, box[1] + 4, box[2] + 4, box[3] + 4),
        radius=_BADGE_RADIUS,
        fill=(0, 0, 0, 120),
    )
    draw.rounded_rectangle(box, radius=_BADGE_RADIUS, fill=bg_color)
    draw.text(
        (cx, box_top + box_h // 2), text, font=font, fill=color, anchor="mm"
    )


class _EmojiRenderer:
    """Renders an emoji codepoint to an RGBA image of a requested size."""

    def __init__(self, path: str | None):
        self.path = path or _first_existing(_EMOJI_FONT_CANDIDATES)
        self._ttfont: Any | None = None
        self._cmap: dict[int, Any] | None = None

    def render(self, char: str, size: int) -> Image.Image | None:
        if not self.path or size <= 0:
            return None
        glyph_name = self._glyph_name(char)
        if glyph_name is None:
            return None
        bitmap = self._sbix_bitmap(glyph_name, size)
        if bitmap is None:
            bitmap = self._cbdt_bitmap(glyph_name)
        if bitmap is None:
            bitmap = self._pil_mask(char, size)
        if bitmap is None:
            return None
        if bitmap.size != (size, size):
            bitmap = bitmap.resize((size, size), Image.LANCZOS)
        return bitmap

    def _font(self) -> Any | None:
        if self._ttfont is not None:
            return self._ttfont
        try:
            from fontTools.ttLib import TTFont

            self._ttfont = TTFont(self.path, fontNumber=0)
            self._cmap = self._ttfont.getBestCmap()
        except Exception:
            self._ttfont = False
        return self._ttfont or None

    def _glyph_name(self, char: str) -> str | None:
        codepoint = _base_codepoint(char)
        if codepoint is None:
            return None
        if self._cmap is None:
            if self._font() is None:
                return None
        if not self._cmap or codepoint not in self._cmap:
            return None
        return self._cmap[codepoint]

    def _sbix_bitmap(self, glyph_name: str, size: int) -> Image.Image | None:
        font = self._font()
        if not font or "sbix" not in font:
            return None
        try:
            strikes = font["sbix"].strikes
            available = [
                ppem
                for ppem, strike in strikes.items()
                if glyph_name in strike.glyphs
            ]
            if not available:
                return None
            strike = strikes[min(available, key=lambda p: abs(p - size))]
            data = strike.glyphs[glyph_name].imageData
            return Image.open(BytesIO(data)).convert("RGBA")
        except Exception:
            return None

    def _cbdt_bitmap(self, glyph_name: str) -> Image.Image | None:
        font = self._font()
        if not font or "CBDT" not in font:
            return None
        try:
            data = font["CBDT"].data.get(glyph_name)
            if not data:
                return None
            return Image.open(BytesIO(data)).convert("RGBA")
        except Exception:
            return None

    def _pil_mask(self, char: str, size: int) -> Image.Image | None:
        try:
            font = ImageFont.truetype(self.path, size=size)
        except Exception:
            return None
        mask = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(mask)
        draw.text((size, size), char, font=font, fill=(255, 255, 255, 255), anchor="mm")
        bbox = mask.getbbox()
        if bbox is None:
            return None
        return mask.crop(bbox)


def _base_codepoint(char: str) -> int | None:
    for cp in char:
        if ord(cp) not in (0xFE0E, 0xFE0F, 0x200D):
            return ord(cp)
    return None


def _load_emoji_font(path: str | None) -> _EmojiRenderer:
    return _EmojiRenderer(path)


def _load_text_font(size: int, path: str | None = None):
    font_path = path or _first_existing(_TEXT_FONT_CANDIDATES)
    if font_path is None:
        return None
    try:
        return ImageFont.truetype(font_path, size=size)
    except Exception:
        return None


def _first_existing(candidates: tuple[str, ...]) -> str | None:
    for path in candidates:
        if os.path.exists(path):
            return path
    return None
