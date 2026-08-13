from dataclasses import dataclass, field
from typing import Any

FORMAT_PORTRAIT = "9:16"
FORMAT_LANDSCAPE = "16:9"
FORMAT_ORIGINAL = "original"

VALID_FORMATS = frozenset((FORMAT_PORTRAIT, FORMAT_LANDSCAPE, FORMAT_ORIGINAL))


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
class Preset:
    id: str
    label: str
    description: str
    target_duration: int
    format: str = FORMAT_PORTRAIT
    keywords: tuple[str, ...] = ()
    caption_style: CaptionStyleConfig = field(default_factory=CaptionStyleConfig)
    zoom: ZoomConfig = field(default_factory=ZoomConfig)
    transitions: TransitionConfig = field(default_factory=TransitionConfig)
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    overlays: OverlayConfig = field(default_factory=OverlayConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)


PRESETS: tuple[Preset, ...] = (
    Preset(
        id="podcast",
        label="Podcast",
        description="Conversational talking-head moments, longer-form hooks.",
        target_duration=45,
        format=FORMAT_LANDSCAPE,
        keywords=("talk", "interview", "conversation", "podcast", "discussion"),
        caption_style=CaptionStyleConfig(
            font="Noto Sans",
            active_color="FFFFFF",
            animation="fade",
        ),
        zoom=ZoomConfig(
            enabled=True,
            punch_zoom_scale=1.1,
            punch_zoom_duration=0.4,
            emphasis_zoom_enabled=True,
            emphasis_zoom_scale=1.12,
        ),
        transitions=TransitionConfig(enabled=False),
        audio=AudioConfig(music_enabled=True, music_volume_db=-20, sfx_enabled=True),
    ),
    Preset(
        id="storytelling",
        label="Storytelling",
        description="Narrative arcs with a setup, turn, and payoff.",
        target_duration=40,
        format=FORMAT_PORTRAIT,
        keywords=("story", "narrative", "journey", "arc", "twist"),
        caption_style=CaptionStyleConfig(
            font="Noto Serif",
            active_color="FFD700",
            animation="typewriter",
        ),
        zoom=ZoomConfig(
            enabled=True,
            emphasis_zoom_enabled=True,
            emphasis_zoom_scale=1.12,
        ),
        transitions=TransitionConfig(type="crossfade", duration=0.8),
        audio=AudioConfig(music_enabled=True, music_volume_db=-18),
    ),
    Preset(
        id="tutorial",
        label="Tutorial",
        description="Step-by-step how-to moments with a clear result.",
        target_duration=40,
        format=FORMAT_PORTRAIT,
        keywords=("how to", "tutorial", "step", "guide", "learn", "tip", "trick"),
        caption_style=CaptionStyleConfig(
            font="Noto Sans",
            active_color="4DD0E1",
            animation="highlight",
        ),
        zoom=ZoomConfig(
            enabled=True,
            punch_zoom_scale=1.2,
            auto_zoom_on_keywords=True,
        ),
        overlays=OverlayConfig(lower_thirds_enabled=True),
        audio=AudioConfig(music_enabled=True, music_volume_db=-22),
    ),
    Preset(
        id="reaction",
        label="Reaction",
        description="Emotional response moments that reward immediate curiosity.",
        target_duration=30,
        format=FORMAT_PORTRAIT,
        keywords=("reaction", "surprised", "shock", "wow", "laugh"),
        caption_style=CaptionStyleConfig(
            font="Noto Sans",
            active_color="FFEB3B",
            font_size_scale=0.04,
            animation="bounce",
        ),
        zoom=ZoomConfig(
            enabled=True,
            punch_zoom_scale=1.25,
            punch_zoom_duration=0.2,
        ),
        overlays=OverlayConfig(emojis_enabled=True, emoji_scale=0.1),
        transitions=TransitionConfig(type="zoom", duration=0.3),
        audio=AudioConfig(music_enabled=False, sfx_enabled=True),
    ),
    Preset(
        id="commentary",
        label="Commentary",
        description="Opinionated hot-takes and analysis that spark debate.",
        target_duration=35,
        format=FORMAT_PORTRAIT,
        keywords=("opinion", "take", "controversial", "analysis", "debate"),
        caption_style=CaptionStyleConfig(
            font="Noto Sans",
            active_color="FF9800",
            animation="slide",
        ),
        zoom=ZoomConfig(
            enabled=True,
            emphasis_zoom_enabled=True,
        ),
        overlays=OverlayConfig(lower_thirds_enabled=True, cta_enabled=True, cta_text="SUBSCRIBE"),
        transitions=TransitionConfig(type="slide", duration=0.4),
        audio=AudioConfig(music_enabled=True, music_volume_db=-16),
    ),
    Preset(
        id="motivational",
        label="Motivational",
        description="Inspirational beats with a strong emotional push.",
        target_duration=30,
        format=FORMAT_PORTRAIT,
        keywords=("motivat", "inspir", "discipline", "mindset", "grind", "believe"),
        caption_style=CaptionStyleConfig(
            font="Noto Sans",
            active_color="FFD54F",
            font_size_scale=0.038,
            animation="glow",
        ),
        zoom=ZoomConfig(
            enabled=True,
            punch_zoom_scale=1.15,
            emphasis_zoom_enabled=True,
            emphasis_zoom_scale=1.1,
        ),
        overlays=OverlayConfig(emojis_enabled=True, cta_enabled=True, cta_text="FOLLOW FOR MORE"),
        audio=AudioConfig(music_enabled=True, music_volume_db=-14, sfx_enabled=True),
    ),
    Preset(
        id="mrbeast",
        label="MrBeast",
        description="High-energy, fast-paced, maximum retention style.",
        target_duration=45,
        format=FORMAT_PORTRAIT,
        keywords=("challenge", "extreme", "crazy", "insane", "giveaway", "reward"),
        caption_style=CaptionStyleConfig(
            font="Noto Sans",
            active_color="FF0000",
            font_size_scale=0.045,
            animation="bounce",
            bold_active=True,
        ),
        zoom=ZoomConfig(
            enabled=True,
            punch_zoom_scale=1.3,
            punch_zoom_duration=0.15,
            emphasis_zoom_enabled=True,
            emphasis_zoom_scale=1.2,
            auto_zoom_on_keywords=True,
        ),
        transitions=TransitionConfig(type="glitch", duration=0.2),
        overlays=OverlayConfig(
            emojis_enabled=True,
            emoji_scale=0.12,
            gifs_enabled=True,
            lower_thirds_enabled=True,
            cta_enabled=True,
            cta_text="SUBSCRIBE NOW",
        ),
        audio=AudioConfig(
            music_enabled=True,
            music_volume_db=-12,
            music_duck_db=-20,
            sfx_enabled=True,
        ),
    ),
    Preset(
        id="hormozi",
        label="Alex Hormozi",
        description="Direct, punchy, conversion-focused style.",
        target_duration=35,
        format=FORMAT_PORTRAIT,
        keywords=("business", "sales", "money", "scale", "strategy", "framework"),
        caption_style=CaptionStyleConfig(
            font="Noto Sans",
            active_color="FFFF00",
            font_size_scale=0.04,
            animation="highlight",
            bold_active=True,
        ),
        zoom=ZoomConfig(
            enabled=True,
            punch_zoom_scale=1.15,
            emphasis_zoom_enabled=True,
            emphasis_zoom_scale=1.1,
        ),
        overlays=OverlayConfig(
            lower_thirds_enabled=True,
            cta_enabled=True,
            cta_text="FREE COURSE IN BIO",
        ),
        audio=AudioConfig(music_enabled=False),
    ),
    Preset(
        id="minimal",
        label="Minimal",
        description="Clean, distraction-free, content-first.",
        target_duration=60,
        format=FORMAT_ORIGINAL,
        keywords=("clean", "simple", "minimal", "aesthetic", "calm"),
        caption_style=CaptionStyleConfig(
            font="Noto Sans",
            active_color="FFFFFF",
            font_size_scale=0.025,
            animation="fade",
        ),
        zoom=ZoomConfig(enabled=False),
        transitions=TransitionConfig(enabled=False),
        audio=AudioConfig(music_enabled=False),
    ),
    Preset(
        id="gaming",
        label="Gaming",
        description="High-energy gameplay with gamer aesthetics.",
        target_duration=40,
        format=FORMAT_PORTRAIT,
        keywords=("gaming", "gameplay", "streamer", "clutch", "highlight", "fps"),
        caption_style=CaptionStyleConfig(
            font="Orbitron",
            active_color="00FF00",
            font_size_scale=0.035,
            animation="glitch",
        ),
        zoom=ZoomConfig(
            enabled=True,
            punch_zoom_scale=1.25,
            punch_zoom_duration=0.1,
        ),
        transitions=TransitionConfig(type="glitch", duration=0.15),
        overlays=OverlayConfig(emojis_enabled=True, gifs_enabled=True),
        background=BackgroundConfig(type="blur", blur_strength=30),
        audio=AudioConfig(music_enabled=False, sfx_enabled=True),
    ),
    Preset(
        id="documentary",
        label="Documentary",
        description="Cinematic, Ken Burns style, authoritative.",
        target_duration=60,
        format=FORMAT_LANDSCAPE,
        keywords=("documentary", "history", "science", "nature", "explained"),
        caption_style=CaptionStyleConfig(
            font="Noto Serif",
            active_color="FFFFFF",
            font_size_scale=0.03,
            animation="fade",
            alignment=8,
        ),
        zoom=ZoomConfig(
            enabled=True,
            emphasis_zoom_enabled=True,
            emphasis_zoom_scale=1.05,
            emphasis_zoom_duration=3.0,
        ),
        transitions=TransitionConfig(type="crossfade", duration=1.5),
        background=BackgroundConfig(type="color", color="000000"),
        audio=AudioConfig(music_enabled=True, music_volume_db=-24),
    ),
    Preset(
        id="business",
        label="Business",
        description="Professional, branded, conversion-oriented.",
        target_duration=45,
        format=FORMAT_PORTRAIT,
        keywords=("business", "startup", "entrepreneur", "leadership", "growth"),
        caption_style=CaptionStyleConfig(
            font="Inter",
            active_color="0066CC",
            font_size_scale=0.033,
            animation="slide",
        ),
        zoom=ZoomConfig(
            enabled=True,
            punch_zoom_scale=1.1,
            emphasis_zoom_enabled=True,
        ),
        overlays=OverlayConfig(
            lower_thirds_enabled=True,
            cta_enabled=True,
            cta_text="BOOK A CALL",
        ),
        transitions=TransitionConfig(type="wipe", duration=0.5),
        audio=AudioConfig(music_enabled=True, music_volume_db=-20),
    ),
)

_DEFAULT_PRESET_ID = "podcast"
_PRESET_BY_ID = {p.id: p for p in PRESETS}


def get_preset(preset_id: str) -> Preset | None:
    return _PRESET_BY_ID.get(preset_id)


def format_for_preset(preset_id: str | None) -> str:
    """Resolve the output aspect ratio for a preset id, defaulting to
    keeping the source format for unknown/absent ids."""
    if preset_id is None:
        return FORMAT_ORIGINAL
    preset = _PRESET_BY_ID.get(preset_id)
    return preset.format if preset is not None else FORMAT_ORIGINAL


def list_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "label": p.label,
            "description": p.description,
            "target_duration": p.target_duration,
            "format": p.format,
            "caption_style": p.caption_style.__dict__,
            "zoom": p.zoom.__dict__,
            "transitions": p.transitions.__dict__,
            "background": p.background.__dict__,
            "overlays": p.overlays.__dict__,
            "audio": p.audio.__dict__,
        }
        for p in PRESETS
    ]


def _score_topics(preset: Preset, topics: list[str]) -> int:
    haystack = " ".join(topics).lower()
    return sum(1 for kw in preset.keywords if kw in haystack)


def recommend_preset(
    understanding: dict[str, Any],
    ai_preset: str | None,
    requested_preset: str | None,
) -> tuple[str, float]:
    """Pick the final preset deterministically.

    Priority: an explicitly requested preset (must be valid) > the AI's preset
    (if it is known) > a keyword match against the video's topics > the default.
    Returns (preset_id, confidence) where confidence is 1.0 for explicit
    requests and decays as we fall back through less direct signals.
    """
    if requested_preset is not None:
        if get_preset(requested_preset) is None:
            raise ValueError(f"unknown preset: {requested_preset}")
        return requested_preset, 1.0

    if ai_preset is not None and get_preset(ai_preset) is not None:
        return ai_preset, 0.8

    topics = list(understanding.get("topics") or [])
    if topics:
        scored = [( _score_topics(p, topics), p.id) for p in PRESETS]
        best_score, best_id = max(scored, key=lambda item: item[0])
        if best_score > 0:
            return best_id, 0.6

    return _DEFAULT_PRESET_ID, 0.4
