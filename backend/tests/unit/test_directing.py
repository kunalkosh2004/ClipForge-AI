from clipforge.directing.application.normalizer import normalize_blueprint
from clipforge.directing.application.service import legacy_plan_from_blueprint
from clipforge.directing.domain.blueprint import (
    BlueprintClip,
    ColorGrading,
    EditingBlueprint,
    EditTimeline,
    GlobalStyle,
    MusicStyle,
    SubtitleTheme,
    TimelineEvent,
)


def _blueprint(**overrides: object) -> EditingBlueprint:
    defaults: dict[str, object] = {
        "preset": "podcast",
        "global_style": GlobalStyle(
            color_grading=ColorGrading(contrast=5.0),
            subtitle_theme=SubtitleTheme(
                font="Noto Sans",
                weight="bold",
                colors=["#FFFFFF", "9e9e9e", "000000", "12345"],
            ),
            music=MusicStyle(volume_db=-18.0, mood="upbeat"),
        ),
        "clips": [
            BlueprintClip(
                start_time=0.0,
                end_time=30.0,
                hook="Hook",
                viral_score=80.0,
                retention_score=70.0,
                story_role="hook",
            )
        ],
        "timeline": EditTimeline(
            events=[
                TimelineEvent(
                    track="camera",
                    type="punch_zoom",
                    timestamp=3.0,
                    duration=0.5,
                    parameters={"strength": 0.6},
                    reason="beat drop",
                )
            ]
        ),
    }
    defaults.update(overrides)
    return EditingBlueprint(**defaults)


def _event(
    track: str,
    type_: str,
    timestamp: float = 5.0,
    duration: float = 0.5,
    parameters: dict | None = None,
    reason: str = "r",
) -> TimelineEvent:
    return TimelineEvent(
        track=track,
        type=type_,
        timestamp=timestamp,
        duration=duration,
        parameters=parameters or {},
        reason=reason,
    )


def test_blueprint_validates_raw_ai_json() -> None:
    raw = {
        "preset": "mrbeast",
        "global_style": {
            "style_name": "high energy",
            "color_grading": {"contrast": 20.0, "saturation": 10.0},
            "subtitle_theme": {"animation": "pop", "colors": ["FF0000"]},
            "music": {"mood": "energetic", "volume_db": -12.0},
        },
        "clips": [
            {
                "start_time": "00:05",
                "end_time": "00:35",
                "hook": "Hook",
                "viral_score": 95,
                "retention_score": 90,
                "story_role": "climax",
            }
        ],
        "timeline": {
            "events": [
                {
                    "track": "camera",
                    "type": "punch_zoom",
                    "timestamp": "12.5",
                    "duration": 0.3,
                    "parameters": {"scale": 1.3},
                    "reason": "beat drop",
                }
            ]
        },
    }
    blueprint = EditingBlueprint.model_validate(raw)
    assert blueprint.clips[0].start_time == "00:05"
    assert blueprint.timeline.events[0].timestamp == 12.5
    assert blueprint.global_style.subtitle_theme.animation == "pop"


def test_blueprint_accepts_null_reason_and_track_type() -> None:
    """Gemini occasionally emits `null` for optional string fields; the
    blueprint must not fail validation — the normalizer drops bad events."""
    raw = {
        "preset": "default",
        "global_style": {},
        "clips": [],
        "timeline": {
            "events": [
                {
                    "track": "camera",
                    "type": "punch_zoom",
                    "timestamp": 5.0,
                    "duration": 0.5,
                    "reason": None,
                },
                {
                    "track": None,
                    "type": None,
                    "timestamp": 6.0,
                    "reason": "beat drop",
                },
            ]
        },
    }
    blueprint = EditingBlueprint.model_validate(raw)
    assert blueprint.timeline.events[0].reason == ""
    assert blueprint.timeline.events[1].track == ""
    assert blueprint.timeline.events[1].type == ""
    # the invalid event gets dropped by the normalizer, not the validator
    normalized = normalize_blueprint(blueprint, duration_seconds=30.0)
    assert all(e.track == "camera" for e in normalized.timeline.events)


def test_normalize_clips_clamps_scores_and_dedupes() -> None:
    blueprint = _blueprint(
        clips=[
            BlueprintClip(start_time=0.0, end_time=30.0, viral_score=150.0, retention_score=-5.0),
            BlueprintClip(start_time=40.0, end_time=60.0, viral_score=50.0),
        ]
    )
    result = normalize_blueprint(blueprint, duration_seconds=120.0)
    assert len(result.clips) == 2
    assert result.clips[0].viral_score == 100.0
    assert result.clips[0].retention_score == 0.0


def test_normalize_maps_track_aliases_and_drops_invalid_events() -> None:
    blueprint = _blueprint(
        timeline=EditTimeline(
            events=[
                _event("cam", "punch_zoom", timestamp=2.0),
                _event("captions", "highlight_word", timestamp=4.0),
                _event("unknown_track", "punch_zoom", timestamp=6.0),
                _event("camera", "teleport", timestamp=8.0),
                _event("camera", "shake", timestamp=200.0),
            ]
        )
    )
    result = normalize_blueprint(blueprint, duration_seconds=120.0)
    assert [e.track for e in result.timeline.events] == ["camera", "subtitle"]
    assert result.timeline.events[0].type == "punch_zoom"


def test_normalize_caps_and_sorts_events_deterministically() -> None:
    events = [
        _event("effects", "boom", timestamp=t)
        for t in [30.0, 10.0, 20.0, 5.0, 25.0, 15.0, 1.0, 35.0]
    ]
    events += [_event("cta", "show_cta", timestamp=50.0), _event("emoji", "pop", timestamp=3.0)]
    result = normalize_blueprint(
        _blueprint(timeline=EditTimeline(events=events)), duration_seconds=120.0
    )
    assert [e.track for e in result.timeline.events] == [
        "emoji",
        "effects",
        "effects",
        "effects",
        "effects",
        "effects",
        "effects",
        "effects",
        "effects",
        "cta",
    ]
    effect_times = [e.timestamp for e in result.timeline.events if e.track == "effects"]
    assert effect_times == sorted(effect_times)


def test_normalize_trusts_empty_tracks() -> None:
    blueprint = _blueprint(timeline=EditTimeline(events=[]))
    result = normalize_blueprint(blueprint, duration_seconds=120.0)
    assert result.timeline.events == []
    assert result.global_style.subtitle_theme.font == "Noto Sans"


def test_normalize_sanitizes_global_style() -> None:
    blueprint = _blueprint(
        global_style=GlobalStyle(
            color_grading=ColorGrading(
                brightness=200.0,
                contrast=-200.0,
                temperature=10.0,
                bloom=50.0,
                vignette=300.0,
            ),
            subtitle_theme=SubtitleTheme(
                font="  Noto Serif  ",
                weight="heavy",
                colors=["#FFFFFF", "xyz", "AABBCC", "FFFFFF"],
                highlight_words=["one", "", "two", "one", "three", "four", "five"],
                background="#000000",
            ),
            music=MusicStyle(volume_db=-60.0, bpm=500.0, mood="jazzy"),
        )
    )
    result = normalize_blueprint(blueprint, duration_seconds=120.0)
    style = result.global_style
    assert style.color_grading.brightness == 100.0
    assert style.color_grading.contrast == -100.0
    assert style.color_grading.vignette == 100.0
    assert style.subtitle_theme.font == "Noto Serif"
    assert style.subtitle_theme.weight is None
    assert style.subtitle_theme.colors == ["FFFFFF", "AABBCC"]
    assert style.subtitle_theme.highlight_words == ["one", "two", "three", "four", "five"]
    assert style.subtitle_theme.background == "000000"
    assert style.music.volume_db == -40.0
    assert style.music.bpm == 200.0
    assert style.music.mood is None


def test_normalize_clamps_event_times_and_durations() -> None:
    blueprint = _blueprint(
        timeline=EditTimeline(
            events=[
                _event("camera", "slow_zoom", timestamp=10.0, duration=999.0),
                _event("camera", "hold", timestamp=-3.0),
            ]
        )
    )
    result = normalize_blueprint(blueprint, duration_seconds=120.0)
    assert len(result.timeline.events) == 1
    assert result.timeline.events[0].duration == 30.0


def test_legacy_plan_derivation_windows_events_into_clips() -> None:
    blueprint = _blueprint(
        clips=[
            BlueprintClip(
                start_time=10.0,
                end_time=35.0,
                hook="First",
                thumbnail_text="T1",
                viral_score=90.0,
                retention_score=80.0,
                story_role="hook",
            )
        ],
        timeline=EditTimeline(
            events=[
                _event("camera", "punch_zoom", timestamp=12.0, parameters={"strength": 0.8}),
                _event("camera", "punch_zoom", timestamp=40.0, parameters={"strength": 0.9}),
                _event("emoji", "pop", timestamp=14.0, parameters={"emoji": "🔥"}),
                _event("overlay", "hook", timestamp=10.5, parameters={"text": "ON SCREEN"}),
                _event("cta", "show_cta", timestamp=30.0, parameters={"text": "Follow"}),
                _event("effects", "boom", timestamp=12.0),
                _event("transition", "whip", timestamp=35.0),
            ]
        ),
    )
    plan = legacy_plan_from_blueprint(blueprint)
    clip = plan["clips"][0]
    assert clip["start_time"] == 10.0
    assert clip["emphasis_times"] == [2.0]
    assert clip["emoji_triggers"] == [{"emoji": "🔥", "time": 4.0}]
    assert clip["hook_text"] == "ON SCREEN"
    assert clip["cta_text"] == "Follow"
    assert clip["viral_score"] == 90.0
    assert plan["style"]["punch_zooms"] is True
    assert plan["style"]["transition_style"] == "whip"
    assert plan["style"]["sfx_enabled"] is True
    assert plan["style"]["emojis_enabled"] is True


def test_legacy_plan_empty_blueprint() -> None:
    blueprint = _blueprint(clips=[], timeline=EditTimeline(events=[]))
    plan = legacy_plan_from_blueprint(blueprint)
    assert plan["clips"] == []
    assert plan["virality_index"] == 0.0


def test_normalize_drops_clips_beyond_video_duration() -> None:
    """Clips that start after the real video end must not reach extraction."""
    blueprint = _blueprint(
        clips=[
            BlueprintClip(start_time=58.0, end_time=103.0, hook="valid"),
            BlueprintClip(start_time=232.0, end_time=240.0, hook="beyond eof"),
            BlueprintClip(start_time=150.0, end_time=195.0, hook="overruns end"),
        ]
    )
    result = normalize_blueprint(blueprint, duration_seconds=161.12)
    assert [c.hook for c in result.clips] == ["valid", "overruns end"]
    assert result.clips[-1].start_time == 150.0
    assert result.clips[-1].end_time <= 161.12
