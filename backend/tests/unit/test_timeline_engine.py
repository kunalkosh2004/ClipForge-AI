from clipforge.timeline.domain.engine import (
    MAX_PUNCH_INS,
    build_timeline,
)


def _scene_artifact(*scenes: tuple[float, float]) -> dict:
    return {
        "scenes": [
            {"start_time": start, "end_time": end, "duration": end - start}
            for start, end in scenes
        ],
        "method": "pyscenedetect.content",
        "scene_count": len(scenes),
    }


def _motion_artifact(intervals: list[tuple[float, float]], max_intensity: float) -> dict:
    return {
        "intervals": [
            {"t": t, "intensity": intensity, "dx": 0.0, "dy": 0.0}
            for t, intensity in intervals
        ],
        "sample_fps": 2.0,
        "max_intensity": max_intensity,
        "has_motion": max_intensity > 0.01,
    }


def _beat_artifact(peaks: list[float], bpm: float | None = 120.0) -> dict:
    return {
        "engine": "energy",
        "has_audio": True,
        "peaks": peaks,
        "bpm": bpm,
        "energy": [],
    }


def test_build_timeline_basic_structure() -> None:
    timeline = build_timeline(
        scenes=_scene_artifact((0.0, 5.0), (5.0, 10.0)),
        motion=_motion_artifact([(1.0, 0.8), (3.0, 0.8)], 0.8),
        beats=_beat_artifact([1.0, 2.0, 6.0]),
    )

    assert timeline["schema_version"] == 1
    assert timeline["duration_seconds"] == 10.0
    assert timeline["has_motion"] is True
    assert timeline["has_audio"] is True
    assert timeline["bpm"] == 120.0
    assert timeline["shot_count"] == 2
    assert timeline["cut_points"] == [5.0]
    assert timeline["shots"][0]["start_time"] == 0.0
    assert timeline["shots"][0]["end_time"] == 5.0
    assert timeline["shots"][1]["start_time"] == 5.0


def test_punch_ins_at_beat_drops_without_motion() -> None:
    timeline = build_timeline(
        scenes=_scene_artifact((0.0, 10.0)),
        motion=None,
        beats=_beat_artifact([1.0, 2.0, 8.0]),
    )

    # three beats in one shot: beat_score 1.0 -> emphasis 0.55 each
    assert [p["reason"] for p in timeline["punch_ins"]] == ["beat", "beat", "beat"]
    assert [p["time"] for p in timeline["punch_ins"]] == [1.0, 2.0, 8.0]
    assert all(p["strength"] == 0.55 for p in timeline["punch_ins"])


def test_punch_ins_from_motion_peaks() -> None:
    timeline = build_timeline(
        scenes=_scene_artifact((0.0, 10.0)),
        motion=_motion_artifact(
            [(1.0, 0.2), (2.0, 1.0), (3.0, 0.2), (4.0, 0.2), (5.0, 0.2)], 1.0
        ),
        beats=_beat_artifact([]),
    )

    assert timeline["punch_ins"] == [
        {"time": 2.0, "strength": 1.0, "reason": "motion"}
    ]


def test_beat_and_motion_candidates_dedupe_into_one() -> None:
    timeline = build_timeline(
        scenes=_scene_artifact((0.0, 10.0)),
        motion=_motion_artifact([(2.2, 1.0)], 1.0),
        beats=_beat_artifact([2.0]),
    )

    assert timeline["punch_ins"] == [
        {"time": 2.0, "strength": 1.0, "reason": "beat+motion"}
    ]


def test_emphasis_score_combines_beat_and_motion() -> None:
    timeline = build_timeline(
        scenes=_scene_artifact((0.0, 5.0), (5.0, 10.0)),
        motion=_motion_artifact(
            [(0.5, 1.0), (1.5, 1.0), (2.5, 1.0), (3.5, 1.0), (4.5, 1.0)], 1.0
        ),
        beats=_beat_artifact([1.0, 2.0]),
    )

    busy, calm = timeline["shots"]
    assert busy["emphasis_score"] > calm["emphasis_score"]
    assert busy["motion_score"] == 1.0
    assert calm["motion_score"] == 0.0


def test_cut_points_exclude_final_duration() -> None:
    timeline = build_timeline(
        scenes=_scene_artifact((0.0, 3.0), (3.0, 7.0), (7.0, 10.0)),
        motion=None,
        beats=_beat_artifact([]),
    )
    assert timeline["cut_points"] == [3.0, 7.0]


def test_missing_artifacts_yield_single_empty_shot() -> None:
    timeline = build_timeline(scenes=None, motion=None, beats=None)

    assert timeline["duration_seconds"] == 0.0
    assert timeline["shot_count"] == 1
    assert timeline["shots"][0]["emphasis_score"] == 0.0
    assert timeline["punch_ins"] == []
    assert timeline["cut_points"] == []
    assert timeline["bpm"] is None


def test_punch_ins_are_capped_and_spread() -> None:
    beats = [1.0 + 0.7 * i for i in range(16)]
    timeline = build_timeline(
        scenes=_scene_artifact((0.0, 20.0)),
        motion=None,
        beats=_beat_artifact(beats),
    )

    assert len(timeline["punch_ins"]) <= MAX_PUNCH_INS
    times = [p["time"] for p in timeline["punch_ins"]]
    assert times == sorted(times)
    for prev, current in zip(times, times[1:], strict=False):
        assert current - prev >= 0.6


def test_build_timeline_is_deterministic() -> None:
    kwargs = dict(
        scenes=_scene_artifact((0.0, 5.0), (5.0, 10.0)),
        motion=_motion_artifact([(1.0, 0.9), (3.0, 0.2), (6.0, 0.8)], 0.9),
        beats=_beat_artifact([1.0, 6.0]),
    )
    assert build_timeline(**kwargs) == build_timeline(**kwargs)


def test_weak_emphasis_shot_drops_beat_punch_in() -> None:
    # beat inside a calm shot (motion_score 0, single beat) scores below the
    # MIN_EMPHASIS threshold and must not produce a punch-in
    timeline = build_timeline(
        scenes=_scene_artifact((0.0, 10.0)),
        motion=None,
        beats=_beat_artifact([4.0]),
    )
    assert timeline["punch_ins"] == []
