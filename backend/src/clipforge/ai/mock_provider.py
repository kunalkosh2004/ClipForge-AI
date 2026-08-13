from clipforge.common.ports import (
    AIProvider,
    ClipCandidate,
    EditingPlan,
    EditorStyle,
    Scene,
    Transcript,
    TranscriptSegment,
    VideoInput,
    VideoUnderstanding,
    Word,
)
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


class MockAIProvider(AIProvider):
    """Deterministic provider for tests and local development without an API key."""

    async def analyze_video(self, video: VideoInput) -> VideoUnderstanding:
        duration = video.duration_seconds or 60.0
        return VideoUnderstanding(
            duration_seconds=duration,
            scenes=[
                Scene(start=0.0, end=duration / 3, description="Intro", shot_type="talking_head"),
                Scene(
                    start=duration / 3,
                    end=2 * duration / 3,
                    description="Main point",
                    shot_type="talking_head",
                ),
                Scene(
                    start=2 * duration / 3,
                    end=duration,
                    description="Call to action",
                    shot_type="talking_head",
                ),
            ],
            topics=["mock"],
            sentiment=0.5,
        )

    async def transcribe(self, video: VideoInput) -> Transcript:
        duration = video.duration_seconds or 60.0
        text = "This is a mock transcript for local development."
        tokens = text.split()
        span = max(duration / len(tokens), 0.1) if tokens else 0.0
        words = [
            Word(
                text=token,
                start=round(i * span, 3),
                end=round(min((i + 1) * span, duration), 3),
            )
            for i, token in enumerate(tokens)
        ]
        return Transcript(
            language="en",
            segments=[
                TranscriptSegment(
                    text=text,
                    start=0.0,
                    end=duration,
                    words=words,
                )
            ],
        )

    async def generate_editing_plan(
        self,
        video: VideoInput,
        preset: str | None = None,
        context: VideoUnderstanding | None = None,
        editing_style: str | None = None,
    ) -> EditingPlan:
        duration = video.duration_seconds or 60.0
        return EditingPlan(
            preset=preset or "podcast",
            clips=[
                ClipCandidate(
                    start_time=0.0,
                    end_time=min(30.0, duration),
                    hook="Mock highlight",
                    why_it_is_engaging="Mock reason",
                    viral_score=80.0,
                    emotion="Excited",
                    category="Storytelling",
                    thumbnail_text="Mock Thumbnail",
                    emphasis_times=[3.0, 8.0, 15.0],
                    emoji_triggers=[
                        {"emoji": "🔥", "time": 3.0},
                        {"emoji": "💯", "time": 15.0},
                    ],
                    hook_text="MOCK HOOK",
                    cta_text="Subscribe!",
                )
            ],
            thumbnail_text="Mock Thumbnail",
            virality_index=80.0,
            style=EditorStyle(
                caption_style="karaoke",
                sfx_enabled=True,
                emojis_enabled=True,
                punch_zooms=True,
                cta_text="Follow for more",
            ),
        )

    async def direct(
        self,
        video: VideoInput,
        preset: str | None = None,
        context: VideoUnderstanding | None = None,
        editing_style: str | None = None,
    ) -> EditingBlueprint:
        duration = video.duration_seconds or 60.0
        clip_end = min(30.0, duration)
        cta_time = max(clip_end - 5.0, 0.0)
        return EditingBlueprint(
            preset=preset or "podcast",
            global_style=GlobalStyle(
                style_name="clean podcast",
                color_grading=ColorGrading(
                    style="clean neutral",
                    contrast=5.0,
                    saturation=5.0,
                ),
                subtitle_theme=SubtitleTheme(
                    font="Noto Sans",
                    weight="bold",
                    animation="sweep",
                    colors=["FFFFFF", "9E9E9E", "000000"],
                ),
                music=MusicStyle(
                    mood="upbeat",
                    volume_db=-18.0,
                    ducking_db=-24.0,
                    bpm=120.0,
                ),
                camera_philosophy="steady framing with one emphasis zoom per key moment",
                editing_philosophy="clean karaoke captions, minimal effects",
            ),
            clips=[
                BlueprintClip(
                    start_time=0.0,
                    end_time=clip_end,
                    hook="Mock highlight",
                    thumbnail_text="Mock Thumbnail",
                    viral_score=80.0,
                    retention_score=75.0,
                    story_role="hook",
                )
            ],
            timeline=EditTimeline(
                events=[
                    TimelineEvent(
                        track="camera",
                        type="punch_zoom",
                        timestamp=3.0,
                        duration=0.5,
                        parameters={
                            "strength": 0.6,
                            "scale": 1.15,
                            "anchor_x": 0.5,
                            "anchor_y": 0.5,
                        },
                        reason="emphasize opening claim",
                    ),
                    TimelineEvent(
                        track="subtitle",
                        type="highlight_word",
                        timestamp=4.0,
                        duration=1.0,
                        parameters={"word": "mock"},
                        reason="hook keyword",
                    ),
                    TimelineEvent(
                        track="emoji",
                        type="pop",
                        timestamp=8.0,
                        duration=2.0,
                        parameters={
                            "emoji": "🔥",
                            "position": "center",
                            "scale": 0.1,
                        },
                        reason="energy spike",
                    ),
                    TimelineEvent(
                        track="effects",
                        type="whoosh",
                        timestamp=3.0,
                        duration=0.3,
                        parameters={"kind": "whoosh"},
                        reason="match the zoom",
                    ),
                    TimelineEvent(
                        track="cta",
                        type="show_cta",
                        timestamp=cta_time,
                        duration=5.0,
                        parameters={
                            "text": "Follow for more",
                            "position": "bottom",
                        },
                        reason="retain subscribers",
                    ),
                ]
            ),
        )
