import numpy as np
import pytest

from clipforge.rendering.domain.framing import (
    TrackPoint,
    build_crop_expressions,
    crop_window_for_target,
    evaluate_track,
    fit_points,
)
from clipforge.rendering.infrastructure.framing_analyzer import (
    _roi_for_frame,
    _roi_track,
)

PORTRAIT = 9 / 16


def test_crop_window_landscape_source() -> None:
    window = crop_window_for_target(1920, 1080, PORTRAIT)
    assert window is not None
    assert window.width == 608  # round(1080 * 9/16) -> even
    assert window.height == 1080


def test_crop_window_already_portrait() -> None:
    assert crop_window_for_target(1080, 1920, PORTRAIT) is None


def test_crop_window_4_3_source() -> None:
    window = crop_window_for_target(1440, 1080, PORTRAIT)
    assert window is not None
    assert window.width == 608
    assert window.height == 1080


def test_crop_window_taller_source() -> None:
    window = crop_window_for_target(1080, 2400, PORTRAIT)
    assert window is not None
    assert window.width == 1080
    assert window.height == 1920


def test_crop_window_degenerate() -> None:
    assert crop_window_for_target(0, 0, PORTRAIT) is None


def test_fit_points_clamps_into_bounds() -> None:
    window = crop_window_for_target(1920, 1080, PORTRAIT)
    points = [
        TrackPoint(t=0.0, x=0.0, y=0.9, mode="motion"),
        TrackPoint(t=1.0, x=1.0, y=0.9, mode="motion"),
        TrackPoint(t=2.0, x=0.5, y=0.5, mode="motion"),
    ]
    fitted = fit_points(points, window, 1920, 1080)
    x_lo = (window.width / 2) / 1920
    assert fitted[0].x == pytest.approx(x_lo)
    assert fitted[1].x == pytest.approx(1 - x_lo)
    assert fitted[2].x == pytest.approx(0.5)
    assert fitted[0].y == pytest.approx(0.5)  # full-height window: centered only


def test_fit_points_empty() -> None:
    assert fit_points([], crop_window_for_target(1920, 1080, PORTRAIT), 1920, 1080) == []


def test_interpolation_midpoint_is_average() -> None:
    times = [0.0, 10.0]
    values = [304.0, 1616.0]
    assert evaluate_track(times, values, 0.0) == pytest.approx(304.0)
    assert evaluate_track(times, values, 10.0) == pytest.approx(1616.0)
    assert evaluate_track(times, values, 5.0) == pytest.approx(960.0)
    assert evaluate_track(times, values, -3.0) == pytest.approx(304.0)
    assert evaluate_track(times, values, 20.0) == pytest.approx(1616.0)


def test_interpolation_piecewise() -> None:
    times = [0.0, 5.0, 15.0]
    values = [0.0, 100.0, 400.0]
    assert evaluate_track(times, values, 2.5) == pytest.approx(50.0)
    assert evaluate_track(times, values, 10.0) == pytest.approx(250.0)


def test_expressions_contain_piecewise_segments() -> None:
    points = [
        TrackPoint(t=0.0, x=304 / 1920, y=0.5),
        TrackPoint(t=5.0, x=960 / 1920, y=0.5),
        TrackPoint(t=10.0, x=1616 / 1920, y=0.5),
    ]
    window = crop_window_for_target(1920, 1080, PORTRAIT)
    x_expr, y_expr = build_crop_expressions(points, window, 1920, 1080)
    assert "if(lt(t" in x_expr
    assert "3-2*" in x_expr  # smoothstep
    assert "0.0000" in x_expr  # 304 (center) - 304 (half window)
    assert "1312.0000" in x_expr  # 1616 - 304
    assert "0.0000" in y_expr  # full-height window: y pinned at top-left corner


def test_expression_single_keyframe_is_constant() -> None:
    points = [TrackPoint(t=2.0, x=0.5, y=0.5)]
    window = crop_window_for_target(1920, 1080, PORTRAIT)
    x_expr, _ = build_crop_expressions(points, window, 1920, 1080)
    assert x_expr == "656.0000"  # center (960) - half window (304)


def test_motion_roi_tracks_moving_box() -> None:
    frames = []
    for i in range(24):
        frame = np.full((60, 120), 32, dtype=np.uint8)
        x0 = 20 + i * 3
        frame[15:45, x0 : x0 + 20] = 220
        frames.append(frame)
    points = _roi_track(frames, None)
    assert len(points) == 23  # first frame has no predecessor for a motion diff
    assert all(p.mode == "motion" for p in points)
    xs = [p.x for p in points]
    assert xs[0] < xs[-1]
    assert xs == sorted(xs)


def test_motion_roi_static_scene_yields_nothing() -> None:
    frame = np.full((60, 120), 32, dtype=np.uint8)
    frame[15:45, 20:40] = 220
    frames = [frame.copy() for _ in range(10)]
    assert _roi_track(frames, None) == []


def test_roi_for_frame_low_motion_returns_none() -> None:
    frame = np.full((60, 120), 32, dtype=np.uint8)
    assert _roi_for_frame(frame, frame.copy(), None) is None
