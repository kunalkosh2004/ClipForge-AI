"""Overlay engine for emojis, GIFs, lower thirds, and CTAs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from clipforge.rendering.domain.styles import OverlayConfig


@dataclass(frozen=True)
class EmojiOverlay:
    emoji: str
    time: float
    duration: float = 2.0
    x: float = 0.5
    y: float = 0.5
    scale: float = 0.08


@dataclass(frozen=True)
class LowerThird:
    text: str
    start_time: float
    end_time: float
    position: str = "bottom"
    font: str = "Noto Sans"
    font_size: int = 48
    color: str = "FFFFFF"
    bg_color: str = "000000CC"


@dataclass(frozen=True)
class CTAOverlay:
    text: str
    start_time: float
    end_time: float
    position: str = "bottom"
    font: str = "Noto Sans"
    font_size: int = 56
    color: str = "FFFFFF"
    bg_color: str = "FF0000CC"


@dataclass(frozen=True)
class OverlayPlan:
    emojis: list[EmojiOverlay] = field(default_factory=list)
    lower_thirds: list[LowerThird] = field(default_factory=list)
    ctas: list[CTAOverlay] = field(default_factory=list)

    def to_ass_events(self, canvas_width: int, canvas_height: int) -> list[str]:
        """Overlay events as ASS Dialogue lines.

        They reference the ``Emoji`` / ``LowerThird`` / ``CTA`` styles, which
        every header that carries overlays must define (see ``ass_header`` and
        ``inject_overlay_styles``).
        """
        events = []

        for emoji in self.emojis:
            fs = int(canvas_height * emoji.scale)
            x_pos = int(canvas_width * emoji.x)
            y_pos = int(canvas_height * emoji.y)
            events.append(
                f"Dialogue: 0,{_ass_time(emoji.time)},{_ass_time(emoji.time + emoji.duration)},"
                f"Emoji,,0,0,0,,{{\\an5\\fs{fs}\\pos({x_pos},{y_pos})}}{emoji.emoji}"
            )

        for lt in self.lower_thirds:
            fs = lt.font_size
            alignment = 2 if lt.position == "bottom" else 8
            events.append(
                f"Dialogue: 0,{_ass_time(lt.start_time)},{_ass_time(lt.end_time)},"
                f"LowerThird,,0,0,0,,{{\\an{alignment}\\fs{fs}\\1c&H{_ass_color(lt.color)}&"
                f"\\3c&H{_ass_color(lt.bg_color)}&\\4c&H{_ass_color(lt.bg_color)}&"
                f"\\bord2\\shad1}}{lt.text}"
            )

        for cta in self.ctas:
            fs = cta.font_size
            alignment = 2 if cta.position == "bottom" else 8
            events.append(
                f"Dialogue: 0,{_ass_time(cta.start_time)},{_ass_time(cta.end_time)},"
                f"CTA,,0,0,0,,{{\\an{alignment}\\fs{fs}\\1c&H{_ass_color(cta.color)}&"
                f"\\3c&H{_ass_color(cta.bg_color)}&\\4c&H{_ass_color(cta.bg_color)}&"
                f"\\b1\\bord3\\shad2}}{cta.text}"
            )

        return events


def _ass_time(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    centis = int(round(seconds * 100))
    hours, centis = divmod(centis, 360000)
    minutes, centis = divmod(centis, 6000)
    secs, centis = divmod(centis, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _ass_color(rgb_hex: str) -> str:
    if rgb_hex.startswith("#"):
        rgb_hex = rgb_hex[1:]
    if len(rgb_hex) == 8:
        a = rgb_hex[6:8]
        rgb_hex = rgb_hex[:6]
    else:
        a = "00"
    r, g, b = rgb_hex[0:2], rgb_hex[2:4], rgb_hex[4:6]
    return f"&H{a}{b}{g}{r}&"


class OverlayEngine:
    def __init__(self, config: OverlayConfig):
        self.config = config

    def build_plan(
        self,
        clip_duration: float,
        emoji_triggers: list[dict[str, Any]] | None = None,
        lower_third_text: str | None = None,
        cta_text: str | None = None,
    ) -> OverlayPlan:
        plan = OverlayPlan()

        if self.config.emojis_enabled and emoji_triggers:
            for trigger in emoji_triggers:
                plan.emojis.append(EmojiOverlay(
                    emoji=trigger.get("emoji", "✨"),
                    time=trigger.get("time", 0),
                    duration=trigger.get("duration", 2.0),
                    x=trigger.get("x", 0.5),
                    y=trigger.get("y", 0.5),
                    scale=self.config.emoji_scale,
                ))

        if self.config.lower_thirds_enabled and lower_third_text:
            plan.lower_thirds.append(LowerThird(
                text=lower_third_text,
                start_time=0,
                end_time=min(5.0, clip_duration),
            ))

        if self.config.cta_enabled and (cta_text or self.config.cta_text):
            text = cta_text or self.config.cta_text
            plan.ctas.append(CTAOverlay(
                text=text,
                start_time=max(0, clip_duration - 5),
                end_time=clip_duration,
            ))

        return plan