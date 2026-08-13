from clipforge.plugins.application.compile import compile_clip_events


def _event(track: str, type: str, timestamp: float, parameters: dict | None = None):
    return {
        "track": track,
        "type": type,
        "timestamp": timestamp,
        "parameters": parameters or {},
        "reason": "test",
    }


def _blueprint(events: list[dict]) -> dict:
    return {"timeline": {"events": events}}


def test_groups_in_window_events_per_track_and_shifts_time() -> None:
    blueprint = _blueprint(
        [
            _event("camera", "punch_in", 5.0),
            _event("camera", "punch_in", 1.0),
            _event("emoji", "emoji", 3.0),
        ]
    )
    grouped = compile_clip_events(blueprint, clip_start=2.0, clip_end=6.0)
    assert set(grouped) == {"camera", "emoji"}
    times = sorted(e.timestamp for e in grouped["camera"])
    assert times == [3.0]
    assert grouped["emoji"][0].timestamp == 1.0


def test_excludes_events_outside_window() -> None:
    blueprint = _blueprint(
        [
            _event("camera", "punch_in", 1.5),
            _event("camera", "punch_in", 2.0),
            _event("camera", "punch_in", 6.0),
        ]
    )
    grouped = compile_clip_events(blueprint, clip_start=2.0, clip_end=6.0)
    # window is [start, end): the event exactly at 6.0 is excluded
    assert [e.timestamp for e in grouped.get("camera", [])] == [0.0]


def test_excludes_transition_tracks_per_clip() -> None:
    blueprint = _blueprint([_event("transition", "fade", 3.0)])
    assert compile_clip_events(blueprint, 2.0, 6.0) == {}


def test_empty_blueprint_yields_no_events() -> None:
    assert compile_clip_events(None, 0.0, 10.0) == {}
    assert compile_clip_events({}, 0.0, 10.0) == {}
    assert compile_clip_events({"timeline": {"events": []}}, 0.0, 10.0) == {}


def test_malformed_events_are_skipped() -> None:
    blueprint = _blueprint(
        [
            {"track": "camera"},  # no timestamp/type
            _event("camera", "punch_in", "not-a-number"),
            _event("camera", "punch_in", 3.0),
            "garbage",
        ]
    )
    grouped = compile_clip_events(blueprint, 2.0, 6.0)
    assert len(grouped["camera"]) == 1
    assert grouped["camera"][0].type == "punch_in"
    assert grouped["camera"][0].timestamp == 1.0


def test_preserves_parameters_and_duration() -> None:
    blueprint = _blueprint(
        [_event("sfx", "sfx", 4.0, {"kind": "boom", "volume_db": -3.0})]
    )
    grouped = compile_clip_events(blueprint, 2.0, 6.0)
    event = grouped["sfx"][0]
    assert event.parameters == {"kind": "boom", "volume_db": -3.0}
    assert event.reason == "test"


def test_bad_parameters_fall_back_to_empty_dict() -> None:
    blueprint = {"timeline": {"events": [_event("emoji", "emoji", 3.0, "oops")]}}
    grouped = compile_clip_events(blueprint, 2.0, 6.0)
    assert grouped["emoji"][0].parameters == {}
