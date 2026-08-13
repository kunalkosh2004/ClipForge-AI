"""Rendering style configurations for editing presets."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class CaptionStyleConfig:
    font: str = "Noto Sans"
    font_size_scale: float = 0.0333
    active_color: str = "FFFFFF"
    muted_color: str = "9E9E9E"
    outline_color: str = "000000"
    margin_v_scale: float = 0.0833
    alignment: int = 2
    bold_active: bool = True
    word_by_word: bool = True
    animation: str = "sweep"
    face_margin: float = 16.0


@dataclass(frozen=True)
class ZoomConfig:
    enabled: bool = False
    punch_zoom_enabled: bool = False
    punch_zoom_scale: float = 1.15
    punch_zoom_duration: float = 0.3
    emphasis_zoom_enabled: bool = False
    emphasis_zoom_scale: float = 1.1
    emphasis_zoom_duration: float = 0.5
    auto_zoom_on_keywords: bool = False


@dataclass(frozen=True)
class TransitionConfig:
    enabled: bool = False
    type: str = "cut"
    duration: float = 0.5
    easing: str = "smoothstep"


@dataclass(frozen=True)
class BackgroundConfig:
    type: str = "none"
    blur_strength: int = 0
    color: str | None = None


@dataclass(frozen=True)
class OverlayConfig:
    emojis_enabled: bool = False
    emoji_scale: float = 0.08
    gifs_enabled: bool = False
    lower_thirds_enabled: bool = False
    cta_enabled: bool = False
    cta_text: str = ""
    cta_position: str = "bottom"


@dataclass(frozen=True)
class AudioConfig:
    music_enabled: bool = False
    music_volume_db: float = -18.0
    music_duck_db: float = -24.0
    sfx_enabled: bool = False


@dataclass(frozen=True)
class RenderStyle:
    caption: CaptionStyleConfig = field(default_factory=CaptionStyleConfig)
    zoom: ZoomConfig = field(default_factory=ZoomConfig)
    transitions: TransitionConfig = field(default_factory=TransitionConfig)
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    overlays: OverlayConfig = field(default_factory=OverlayConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "caption": self.caption.__dict__,
            "zoom": self.zoom.__dict__,
            "transitions": self.transitions.__dict__,
            "background": self.background.__dict__,
            "overlays": self.overlays.__dict__,
            "audio": self.audio.__dict__,
        }

    @classmethod
    def from_preset(cls, preset) -> RenderStyle:
        return cls(
            caption=preset.caption_style,
            zoom=ZoomConfig(
                punch_zoom_enabled=preset.zoom.enabled,
                punch_zoom_scale=preset.zoom.punch_zoom_scale,
                punch_zoom_duration=preset.zoom.punch_zoom_duration,
                emphasis_zoom_enabled=preset.zoom.emphasis_zoom_enabled,
                emphasis_zoom_scale=preset.zoom.emphasis_zoom_scale,
                emphasis_zoom_duration=preset.zoom.emphasis_zoom_duration,
                auto_zoom_on_keywords=preset.zoom.auto_zoom_on_keywords,
            ),
            transitions=preset.transitions,
            background=preset.background,
            overlays=preset.overlays,
            audio=preset.audio,
        )


def apply_style_overrides(style: RenderStyle, overrides: dict[str, Any]) -> RenderStyle:
    """Apply plan-level editor directives over a preset-derived RenderStyle.

    `overrides` mirrors the AI's `EditorStyle` output (e.g.
    `{"caption_colors": ["FFD700"], "punch_zooms": true, ...}`). Every key is
    optional and unknown keys are ignored, so a bare request degrades to the
    preset defaults.
    """
    if not overrides:
        return style

    caption = style.caption
    colors = overrides.get("caption_colors") or []
    if overrides.get("caption_style"):
        caption = replace(
            caption, animation=_caption_animation(str(overrides["caption_style"]))
        )
    if colors:
        accent = str(colors[0]).lstrip("#")
        if len(accent) == 6:
            caption = replace(caption, active_color=accent.upper())
    if len(colors) >= 2:
        muted = str(colors[1]).lstrip("#")
        if len(muted) == 6:
            caption = replace(caption, muted_color=muted.upper())
    if len(colors) >= 3:
        outline = str(colors[2]).lstrip("#")
        if len(outline) == 6:
            caption = replace(caption, outline_color=outline.upper())

    zoom = style.zoom
    zoom_overrides: dict[str, Any] = {}
    if overrides.get("punch_zooms") is True:
        zoom_overrides["enabled"] = True
        zoom_overrides["punch_zoom_enabled"] = True
    if overrides.get("zoom_intensity") is not None:
        try:
            intensity = min(max(float(overrides["zoom_intensity"]), 0.0), 1.0)
        except (TypeError, ValueError):
            intensity = 0.0
        zoom_overrides["enabled"] = True
        zoom_overrides["punch_zoom_enabled"] = True
        zoom_overrides["emphasis_zoom_enabled"] = True
        zoom_overrides["punch_zoom_scale"] = round(1.05 + 0.3 * intensity, 3)
        zoom_overrides["emphasis_zoom_scale"] = round(1.05 + 0.2 * intensity, 3)
    if zoom_overrides:
        zoom = replace(zoom, **zoom_overrides)

    transitions = style.transitions
    if overrides.get("transition_style"):
        transition_type = str(overrides["transition_style"]).lower()
        if transition_type not in ("cut", "none"):
            transitions = replace(
                transitions, enabled=True, type=transition_type
            )

    overlays = style.overlays
    overlay_overrides: dict[str, Any] = {}
    if overrides.get("emojis_enabled") is not None:
        overlay_overrides["emojis_enabled"] = bool(overrides["emojis_enabled"])
    if overrides.get("cta_enabled") is not None:
        overlay_overrides["cta_enabled"] = bool(overrides["cta_enabled"])
    if overrides.get("cta_text"):
        overlay_overrides["cta_text"] = str(overrides["cta_text"])[:80]
    if overlay_overrides:
        overlays = replace(overlays, **overlay_overrides)

    audio = style.audio
    audio_overrides: dict[str, Any] = {}
    if overrides.get("sfx_enabled") is not None:
        audio_overrides["sfx_enabled"] = bool(overrides["sfx_enabled"])
    if overrides.get("music_volume_db") is not None:
        with contextlib.suppress(TypeError, ValueError):
            audio_overrides["music_volume_db"] = float(overrides["music_volume_db"])
    if audio_overrides:
        audio = replace(audio, **audio_overrides)

    return replace(
        style,
        caption=caption,
        zoom=zoom,
        transitions=transitions,
        overlays=overlays,
        audio=audio,
    )


def _caption_animation(value: str) -> str:
    return {
        "karaoke": "sweep",
        "word-by-word": "sweep",
        "word": "sweep",
        "sweep": "sweep",
        "typewriter": "typewriter",
        "fade": "fade",
        "pop": "pop",
        "bounce": "pop",
    }.get(value.lower(), value.lower())