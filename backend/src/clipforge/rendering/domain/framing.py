"""Smart re-framing for aspect-ratio conversion.

Given a subject-center track over time, computes a crop window in source
pixels and a pair of ffmpeg ``crop`` filter expressions that glide (piecewise
ease-in-out) so the subject stays framed while a wide source is turned into a
vertical canvas.
"""

from __future__ import annotations

from dataclasses import dataclass

PORTRAIT_ASPECT = 9 / 16


@dataclass(frozen=True)
class TrackPoint:
    """Subject center, normalized to the source frame (0..1)."""

    t: float
    x: float
    y: float
    mode: str = "motion"  # "face" | "motion"


@dataclass(frozen=True)
class CropWindow:
    width: int
    height: int


@dataclass(frozen=True)
class FramingPlan:
    window: CropWindow
    x_expression: str
    y_expression: str


def crop_window_for_target(
    source_width: int,
    source_height: int,
    target_aspect: float,
) -> CropWindow | None:
    """Target-aspect crop window in source pixels (even dimensions).

    Returns None when the source already matches the target aspect or there
    is nothing to crop (so the caller keeps the plain center crop).
    """
    if source_width <= 0 or source_height <= 0 or target_aspect <= 0:
        return None
    source_aspect = source_width / source_height
    if abs(source_aspect - target_aspect) < 1e-3:
        return None
    if source_aspect > target_aspect:
        width = _even(int(round(source_height * target_aspect)))
        height = source_height
    else:
        width = source_width
        height = _even(int(round(source_width / target_aspect)))
    if width >= source_width and height >= source_height:
        return None
    return CropWindow(width=width, height=height)


def fit_points(
    points: list[TrackPoint],
    window: CropWindow,
    source_width: int,
    source_height: int,
) -> list[TrackPoint]:
    """Clamp ROI centers so the crop window stays inside the source frame."""
    if not points:
        return []
    x_lo = (window.width / 2) / source_width
    x_hi = 1.0 - x_lo
    y_lo = (window.height / 2) / source_height
    y_hi = 1.0 - y_lo
    fitted = []
    for p in points:
        fitted.append(
            TrackPoint(
                t=p.t,
                x=min(max(p.x, x_lo), x_hi),
                y=min(max(p.y, y_lo), y_hi),
                mode=p.mode,
            )
        )
    return fitted


def build_crop_expressions(
    points: list[TrackPoint],
    window: CropWindow,
    source_width: int,
    source_height: int,
) -> tuple[str, str]:
    """Return ``(x, y)`` ffmpeg crop expressions in source pixels.

    Crop x/y are the window's *top-left* corner, so the subject center is
    offset by half the window size. Points are assumed already clamped to the
    window bounds via :func:`fit_points`, which keeps the corner inside the
    source. Interpolation is a piecewise smoothstep (ease-in-out) so the crop
    glides between keyframes instead of jumping.
    """
    half_w = window.width / 2
    half_h = window.height / 2
    x_expr = _interp_expression(
        [p.t for p in points],
        [p.x * source_width - half_w for p in points],
        (source_width - window.width) / 2,
    )
    y_expr = _interp_expression(
        [p.t for p in points],
        [p.y * source_height - half_h for p in points],
        (source_height - window.height) / 2,
    )
    return x_expr, y_expr


def evaluate_track(times: list[float], values: list[float], t: float) -> float:
    """Reference evaluator for the piecewise smoothstep interpolation.

    Mirrors exactly what the emitted ffmpeg expression computes; kept as a
    plain function so the math is unit-testable without ffmpeg.
    """
    if not times:
        return 0.0
    if len(times) == 1:
        return values[0]
    if t <= times[0]:
        return values[0]
    if t >= times[-1]:
        return values[-1]
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        if t < t1:
            s = (t - t0) / (t1 - t0)
            step = s * s * (3 - 2 * s)
            return values[i] + (values[i + 1] - values[i]) * step
    return values[-1]


def _interp_expression(
    times: list[float],
    values: list[float],
    fallback: float,
) -> str:
    if not times or not values:
        return f"{fallback:.4f}"
    if len(times) == 1:
        return f"{values[0]:.4f}"
    expr = f"{values[-1]:.4f}"
    for i in range(len(times) - 2, -1, -1):
        t0, t1 = times[i], times[i + 1]
        v0, v1 = values[i], values[i + 1]
        span = t1 - t0
        if span <= 1e-9:
            continue
        s = f"((t-{t0:.4f})/{span:.4f})"
        step = f"({s}*{s}*(3-2*{s}))"
        seg = f"({v0:.4f}+({v1 - v0:.4f})*{step})"
        seg = f"if(lt(t,{t0:.4f}),{v0:.4f},if(gt(t,{t1:.4f}),{v1:.4f},{seg}))"
        expr = f"if(lt(t,{t1:.4f}),{seg},{expr})"
    return expr


def _even(value: int) -> int:
    return value if value % 2 == 0 else value - 1
