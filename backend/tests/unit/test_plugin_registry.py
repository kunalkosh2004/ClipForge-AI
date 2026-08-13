from clipforge.plugins.application.plugins.color import ColorPlugin
from clipforge.plugins.application.plugins.subtitle import SubtitlePlugin
from clipforge.plugins.domain.registry import PluginRegistry, build_default_registry


def test_register_and_resolve() -> None:
    registry = PluginRegistry()
    subtitle = SubtitlePlugin()
    registry.register(subtitle)
    assert registry.resolve("subtitle") is subtitle
    assert registry.resolve("missing") is None
    assert registry.tracks() == ["subtitle"]


def test_aliases_resolve_to_same_instance() -> None:
    registry = PluginRegistry()
    color = ColorPlugin()
    registry.register(color, aliases=("effects",))
    assert registry.resolve("color") is color
    assert registry.resolve("effects") is color
    assert len(registry) == 2


def test_last_registration_wins() -> None:
    registry = PluginRegistry()
    registry.register(SubtitlePlugin())
    second = SubtitlePlugin()
    registry.register(second)
    assert registry.resolve("subtitle") is second


def test_default_registry_has_all_tracks() -> None:
    registry = build_default_registry()
    for track in ("camera", "subtitle", "transition", "overlay", "emoji", "music", "sfx"):
        assert registry.resolve(track) is not None, track
    assert registry.resolve("cta") is not None
    assert registry.resolve("effects") is registry.resolve("color")
