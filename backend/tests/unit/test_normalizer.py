from clipforge.analysis.application.normalizer import normalize_editing_plan
from clipforge.common.ports import ClipCandidate, EditingPlan, EditorStyle


def _plan(clips: list[ClipCandidate]) -> EditingPlan:
    return EditingPlan(
        preset="podcast",
        clips=clips,
        style=EditorStyle(
            caption_style="typewriter",
            punch_zooms=True,
            sfx_enabled=True,
        ),
    )


def test_normalize_keeps_new_per_clip_fields() -> None:
    plan = _plan(
        [
            ClipCandidate(
                start_time="00:10",
                end_time="00:35",
                hook="Hook",
                emphasis_times=[5.0, 2.0],
                emoji_triggers=[{"emoji": "🔥", "time": 3.0}],
                cta_text="Subscribe!",
                hook_text="ON SCREEN HOOK",
            )
        ]
    )

    result = normalize_editing_plan(plan, duration_seconds=120.0)

    clip = result.clips[0]
    assert clip.start_time == 10.0
    assert clip.end_time == 35.0
    assert clip.emphasis_times == [2.0, 5.0]
    assert [(t.emoji, t.time) for t in clip.emoji_triggers] == [("🔥", 3.0)]
    assert clip.cta_text == "Subscribe!"
    assert clip.hook_text == "ON SCREEN HOOK"
    assert result.style is not None
    assert result.style.caption_style == "typewriter"


def test_normalize_drops_out_of_window_emphasis_and_emoji() -> None:
    plan = _plan(
        [
            ClipCandidate(
                start_time=10.0,
                end_time=30.0,
                hook="Hook",
                emphasis_times=[-1.0, 0.0, 5.0, 19.5, 99.0, 5.0],
                emoji_triggers=[
                    {"emoji": "🔥", "time": 2.0},
                    {"emoji": "", "time": 5.0},
                    {"emoji": "💯", "time": 100.0},
                ],
            )
        ]
    )

    result = normalize_editing_plan(plan, duration_seconds=120.0)

    clip = result.clips[0]
    assert clip.emphasis_times == [5.0, 19.5]
    assert [(t.emoji, t.time) for t in clip.emoji_triggers] == [("🔥", 2.0)]


def test_normalize_extends_short_clip_and_keeps_fields() -> None:
    plan = _plan(
        [
            ClipCandidate(
                start_time=10.0,
                end_time=15.0,
                hook="Short",
                emphasis_times=[2.0, 4.0],
                emoji_triggers=[{"emoji": "😂", "time": 1.0}],
                cta_text="Follow",
                hook_text="SHORT HOOK",
            ),
            ClipCandidate(
                start_time=40.0,
                end_time=60.0,
                hook="Next",
            ),
        ]
    )

    result = normalize_editing_plan(plan, duration_seconds=120.0)

    clip = result.clips[0]
    assert clip.end_time - clip.start_time >= 20.0
    assert clip.emphasis_times == [2.0, 4.0]
    assert [(t.emoji, t.time) for t in clip.emoji_triggers] == [("😂", 1.0)]
    assert clip.cta_text == "Follow"
    assert clip.hook_text == "SHORT HOOK"


def test_normalize_preserves_plan_style_when_absent() -> None:
    plan = EditingPlan(
        preset="podcast",
        clips=[ClipCandidate(start_time=0.0, end_time=25.0, hook="h")],
    )

    result = normalize_editing_plan(plan, duration_seconds=60.0)

    assert result.style is None
