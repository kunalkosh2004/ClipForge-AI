"""Shared defensive accessors for plugin event parameters."""

from __future__ import annotations

from typing import Any


def float_param(
    parameters: dict[str, Any], key: str, default: float = 0.0
) -> float:
    value = parameters.get(key)
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default  # NaN guard


def str_param(
    parameters: dict[str, Any], key: str, default: str = ""
) -> str:
    value = parameters.get(key)
    return value if isinstance(value, str) and value else default


def hex_color(value: Any) -> str | None:
    """Validate a 6-hex color (optionally #-prefixed); None otherwise."""
    if not isinstance(value, str):
        return None
    cleaned = value.lstrip("#")
    if len(cleaned) == 6 and all(c in "0123456789abcdefABCDEF" for c in cleaned):
        return cleaned.upper()
    return None


def colors_from(parameters: dict[str, Any]) -> list[str]:
    value = parameters.get("colors")
    if not isinstance(value, list):
        return []
    return [c for c in (hex_color(v) for v in value) if c is not None]
