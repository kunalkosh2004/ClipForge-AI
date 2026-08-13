"""MotionCaption adapter: LyricsRequest → deterministic SubtitleTimeline."""

from __future__ import annotations

from typing import Any

from motion_caption import (
    AIContribution,
    Box,
    CaptionRequest,
    Color,
    CompileOptions,
    EmphasisMode,
    Face,
    PlacementConfig,
    SafeArea,
    ThemeSpec,
    Transcript,
    WordTimestamp,
    load_theme,
)
from motion_caption.animations.engine import AnimationConfig
from motion_caption.compiler import compile
from motion_caption.themes.spec import EmphasisAppearance
from motion_caption.typography.style import FillSpec

from clipforge.lyrics.application.theme import (
    accent_hex,
    animation_strategy,
    theme_name_for,
)
from clipforge.lyrics.domain.entities import CompiledLyrics, LyricsRequest


class MotionCaptionLyricsCompiler:
    """Compiles clip lyrics with the deterministic MotionCaption engine.

    Deterministic by construction: identical requests always produce an
    identical ``SubtitleTimeline`` (the compiler LRU-caches by serialized
    request). No model runs inside the compiler; precomputed emphasis lands
    on the request as ``AIContribution``.
    """

    def compile(self, request: LyricsRequest) -> CompiledLyrics:
        transcript = Transcript(
            words=[
                WordTimestamp(text=word.text, start=word.start, end=word.end)
                for word in request.words
            ]
        )
        theme_name = theme_name_for(request.preset, request.theme)
        theme = _apply_theme_overrides(
            load_theme(theme_name),
            accent=accent_hex(request.accent_color),
            muted=accent_hex(request.muted_color),
        )

        in_bounds = [i for i in request.emphasis_indices if 0 <= i < len(request.words)]
        annotations: AIContribution | None = None
        if in_bounds:
            annotations = AIContribution(
                emphasis={i: EmphasisMode.KARAOKE for i in in_bounds}
            )
        safe_area = (
            SafeArea(
                top=request.safe_area["top"],
                bottom=request.safe_area["bottom"],
                left=request.safe_area["left"],
                right=request.safe_area["right"],
            )
            if request.safe_area is not None
            else None
        )

        caption_request = CaptionRequest(
            transcript=transcript,
            theme=theme,
            resolution=f"{request.canvas_width}x{request.canvas_height}",
            platform=request.platform,
            safe_area=safe_area,
            faces=[
                Face(box=Box(left, top, right, bottom))
                for left, top, right, bottom in request.faces
            ],
            llm_annotations=annotations,
            options=_compile_options(request),
        )
        timeline = compile(caption_request)
        return CompiledLyrics(
            request=request,
            theme_name=theme_name,
            timeline=timeline,
            event_count=len(timeline.events),
            word_count=len(timeline.words),
            duration=timeline.end,
        )


def _compile_options(request: LyricsRequest) -> CompileOptions:
    """Compile options: karaoke + animation strategy, plus face-aware
    placement when face boxes are available."""
    options: dict[str, Any] = {
        "karaoke": request.karaoke,
        "animation": AnimationConfig(
            strategy=animation_strategy(request.animation, request.karaoke)
        ),
    }
    if request.faces:
        options["placement"] = PlacementConfig(
            strategy="face-aware",
            face_margin=request.face_margin,
        )
    return CompileOptions(**options)


def _apply_theme_overrides(
    theme: ThemeSpec, *, accent: str | None, muted: str | None
) -> ThemeSpec:
    """Layer ClipForge caption colors onto a MotionCaption theme.

    ``muted`` becomes the base word fill; ``accent`` becomes the active
    (karaoke/emphasized) word color. Neither field changes the theme's
    motion personality — animation strategy is set per-request instead.
    """
    updates: dict[str, Any] = {}
    style = theme.style
    if muted:
        style = style.model_copy(update={"fill": FillSpec(color=Color(muted))})
        updates["style"] = style

    emphasis = dict(theme.emphasis)
    accent_color = Color(accent) if accent else None
    if accent_color is not None:
        karaoke = emphasis.get(EmphasisMode.KARAOKE)
        if karaoke is not None:
            emphasis[EmphasisMode.KARAOKE] = karaoke.model_copy(
                update={"color": accent_color}
            )
        else:
            emphasis[EmphasisMode.KARAOKE] = EmphasisAppearance(
                color=accent_color
            )
    if emphasis:
        updates["emphasis"] = emphasis

    return theme.model_copy(update=updates) if updates else theme
