from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from clipforge.directing.domain.blueprint import EditingBlueprint


class VideoInput(BaseModel):
    storage_uri: str
    mime_type: str
    duration_seconds: float | None = None


class Word(BaseModel):
    text: str
    start: float
    end: float


class TranscriptSegment(BaseModel):
    text: str
    start: float
    end: float
    speaker: str | None = None
    words: list[Word] = Field(default_factory=list)


class Transcript(BaseModel):
    language: str
    segments: list[TranscriptSegment] = Field(default_factory=list)


class Scene(BaseModel):
    start: float
    end: float
    description: str | None = None
    shot_type: str | None = None


class VideoUnderstanding(BaseModel):
    duration_seconds: float
    scenes: list[Scene] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    sentiment: float = 0.0


class EmojiTrigger(BaseModel):
    """An emoji that pops on screen at a clip-local second."""

    emoji: str
    time: float = 0.0


class ClipCandidate(BaseModel):
    """A viral moment from the source video, in the AI's clip-plan format.

    `start_time`/`end_time` may be numeric seconds or "MM:SS" / "HH:MM:SS" strings.
    `emphasis_times` and `emoji_triggers[*].time` are seconds relative to the
    start of this clip (0.0 = clip start).
    """

    start_time: str | float
    end_time: str | float
    hook: str | None = None
    why_it_is_engaging: str | None = None
    viral_score: float = 0.0
    emotion: str | None = None
    category: str | None = None
    thumbnail_text: str | None = None
    emphasis_times: list[float] = Field(default_factory=list)
    emoji_triggers: list[EmojiTrigger] = Field(default_factory=list)
    cta_text: str | None = None
    hook_text: str | None = None


class EditorStyle(BaseModel):
    """Plan-level editing directives mapped from the user's editing request.

    Every field is optional so a bare request (or none at all) still produces a
    valid plan; the rendering pipeline falls back to the preset's defaults.
    """

    caption_style: str | None = None
    caption_colors: list[str] | None = None
    transition_style: str | None = None
    sfx_enabled: bool | None = None
    sfx_types: list[str] | None = None
    music_mood: str | None = None
    music_volume_db: float | None = None
    emojis_enabled: bool | None = None
    punch_zooms: bool | None = None
    zoom_intensity: float | None = None
    cta_enabled: bool | None = None
    cta_text: str | None = None


class EditingPlan(BaseModel):
    preset: str
    clips: list[ClipCandidate]
    thumbnail_text: str | None = None
    virality_index: float = 0.0
    preset_confidence: float = 1.0
    style: EditorStyle | None = None


class AIModelUsage(BaseModel):
    """Token consumption of a single provider call (for quota UI)."""

    model: str
    operation: str
    prompt_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0
    key: str | None = None


class AIProvider(ABC):
    @abstractmethod
    async def analyze_video(self, video: VideoInput) -> VideoUnderstanding:
        """Multimodal understanding: scenes, topics, and sentiment signal."""

    @abstractmethod
    async def transcribe(self, video: VideoInput) -> Transcript:
        """Word-timestamped transcript with speaker labels."""

    @abstractmethod
    async def generate_editing_plan(
        self,
        video: VideoInput,
        preset: str | None = None,
        context: VideoUnderstanding | None = None,
        editing_style: str | None = None,
    ) -> EditingPlan:
        """Analyze the video and return the list of viral clips that drive editing.

        `context`, when provided, carries the output of `analyze_video` so the
        provider can ground its clip choices in the scenes, topics, and
        sentiment signal already extracted for the same video.

        `editing_style`, when provided, is the user's free-text editing request
        (caption style, transitions, sound effects, etc.) and should steer both
        the plan-level `style` directives and the per-clip fields.
        """

    @abstractmethod
    async def direct(
        self,
        video: VideoInput,
        preset: str | None = None,
        context: VideoUnderstanding | None = None,
        editing_style: str | None = None,
    ) -> EditingBlueprint:
        """Direct the edit: watch the whole video and return an executable
        `EditingBlueprint` (global style + clips + a per-track timeline).

        Every timeline event carries timestamp/duration/parameters/reason; the
        renderer executes them exactly and never makes creative decisions.

        `context`, when provided, carries the output of `analyze_video` so the
        director can ground scene boundaries, hooks and emphasis in the scenes,
        topics and sentiment already extracted for the same video.
        """
