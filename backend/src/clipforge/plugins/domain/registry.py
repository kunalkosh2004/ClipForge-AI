"""Plugin registry: resolve a timeline track to its renderer plugin."""

from __future__ import annotations

from clipforge.plugins.domain.spec import RendererPlugin


class PluginRegistry:
    """Maps track names (and aliases) to plugin instances."""

    def __init__(self) -> None:
        self._plugins: dict[str, RendererPlugin] = {}

    def register(
        self, plugin: RendererPlugin, aliases: tuple[str, ...] = ()
    ) -> None:
        self._plugins[plugin.track] = plugin
        for alias in aliases:
            self._plugins[alias] = plugin

    def resolve(self, track: str) -> RendererPlugin | None:
        return self._plugins.get(track)

    def tracks(self) -> list[str]:
        return sorted(self._plugins)

    def __len__(self) -> int:
        return len(self._plugins)


def build_default_registry() -> PluginRegistry:
    """Registry with every shipped per-track plugin.

    The color plugin also serves the blueprint's ``effects`` track; the
    subtitle/overlay/emoji/music/sfx/cta plugins mirror the M5 track list.
    """
    from clipforge.plugins.application.plugins.camera import CameraPlugin
    from clipforge.plugins.application.plugins.color import ColorPlugin
    from clipforge.plugins.application.plugins.cta import CtaPlugin
    from clipforge.plugins.application.plugins.emoji import EmojiPlugin
    from clipforge.plugins.application.plugins.music import MusicPlugin
    from clipforge.plugins.application.plugins.overlay import OverlayPlugin
    from clipforge.plugins.application.plugins.sfx import SfxPlugin
    from clipforge.plugins.application.plugins.subtitle import SubtitlePlugin
    from clipforge.plugins.application.plugins.transition import TransitionPlugin

    registry = PluginRegistry()
    registry.register(CameraPlugin())
    registry.register(SubtitlePlugin())
    registry.register(TransitionPlugin())
    registry.register(OverlayPlugin())
    registry.register(EmojiPlugin())
    registry.register(ColorPlugin(), aliases=("effects",))
    registry.register(MusicPlugin())
    registry.register(SfxPlugin())
    registry.register(CtaPlugin())
    return registry
