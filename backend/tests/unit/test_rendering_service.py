import io
import uuid
from pathlib import Path

import pytest

from clipforge.analysis.domain.entities import AnalysisResultRecord, TranscriptRecord
from clipforge.analysis.domain.presets import get_preset
from clipforge.clips.domain.entities import Clip
from clipforge.common.ids import uuid7
from clipforge.common.pagination import PageResult
from clipforge.rendering.application.service import RenderingService
from clipforge.rendering.domain.audio import AudioEngine
from clipforge.rendering.domain.styles import RenderStyle
from clipforge.rendering.domain.zoom import ZoomEngine
from clipforge.videos.domain.entities import Video


class FakeClipRepo:
    def __init__(self, clips: list[Clip]) -> None:
        self._clips = clips
        self.updated: list[Clip] = []

    async def list_for_video(self, video_id: uuid.UUID) -> PageResult[Clip]:
        return PageResult(items=self._clips, total=len(self._clips), limit=100, offset=0)

    async def update_render(
        self, clip_id: uuid.UUID, storage_key: str, thumbnail_storage_key: str | None = None
    ) -> Clip | None:
        clip = next((c for c in self._clips if c.id == clip_id), None)
        if clip is not None:
            self.updated.append(clip)
        return clip


class FakeTranscriptRepo:
    def __init__(self, words: list[dict]) -> None:
        self._record = TranscriptRecord(video_id=uuid7(), language="hi", words=words)

    async def get_by_video_id(self, video_id: uuid.UUID) -> TranscriptRecord | None:
        return self._record


class FakeAnalysisRepo:
    def __init__(self, preset: str, blueprint: dict | None = None) -> None:
        self._record = AnalysisResultRecord(
            video_id=uuid7(),
            understanding={},
            editing_plan={"preset": preset},
            editing_blueprint=blueprint,
            ai_model="mock",
        )

    async def get_by_video_id(self, video_id: uuid.UUID) -> AnalysisResultRecord | None:
        return self._record


class FakeVideoRepo:
    def __init__(self, audio: dict) -> None:
        self._video = Video(
            project_id=uuid7(),
            original_filename="mock.mp4",
            storage_key="videos/mock.mp4",
            content_type="video/mp4",
            size_bytes=1,
            metadata_json={"audio": audio},
        )

    async def get_by_id(self, video_id: uuid.UUID) -> Video | None:
        return self._video


class FakeStorage:
    def __init__(self) -> None:
        self.puts: list[tuple[str, str]] = []

    async def get(self, key: str) -> io.BytesIO:
        return io.BytesIO(b"fake-media-bytes")

    async def put(self, key: str, data, content_type: str) -> None:
        self.puts.append((key, content_type))


class FakeThumbnails:
    async def generate(
        self, source_path: str, timestamp_seconds: float, output_path: str
    ) -> None:
        Path(output_path).write_bytes(b"thumb")


class FakeNotifier:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, payload: dict) -> None:
        self.published.append(payload)


def _clip(video_id: uuid.UUID, start: float = 2.0, end: float = 12.0) -> Clip:
    return Clip(
        id=uuid7(),
        video_id=video_id,
        project_id=uuid7(),
        title="Great Moment",
        start_seconds=start,
        end_seconds=end,
        duration_seconds=end - start,
        storage_key="clips/source.mp4",
        status="ready",
        format="16:9",
    )


def _make_service(
    monkeypatch,
    clips: list[Clip],
    audio: dict,
    *,
    caption_engine: str = "legacy",
    words: list[dict] | None = None,
    blueprint: dict | None = None,
) -> tuple[RenderingService, dict]:
    transcript_words = words if words is not None else [
        {"word": "hi", "start": 0, "end": 0.4}
    ]
    service = RenderingService(
        clips=FakeClipRepo(clips),
        transcripts=FakeTranscriptRepo(transcript_words),
        analysis_results=FakeAnalysisRepo("podcast", blueprint=blueprint),
        videos=FakeVideoRepo(audio),
        storage=FakeStorage(),
        renderer=object(),  # CompositeRenderer is monkeypatched below
        thumbnails=FakeThumbnails(),
        notifier=FakeNotifier(),
        framing=None,
        caption_engine=caption_engine,
    )
    captured: dict = {}

    async def fake_render_clip(self, *args, **kwargs) -> None:
        captured.update(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"rendered")

    monkeypatch.setattr(
        "clipforge.rendering.domain.composite.CompositeRenderer.render_clip",
        fake_render_clip,
    )
    return service, captured


@pytest.mark.asyncio
async def test_render_uses_composite_with_beats_music_sfx(monkeypatch) -> None:
    video_id = uuid7()
    clip = _clip(video_id)
    service, captured = _make_service(
        monkeypatch,
        [clip],
        audio={"peaks": [2.5, 7.0, 20.0], "bpm": 120},
    )

    rendered, _ = await service.render_clips_with_captions(video_id)

    assert rendered == 1
    assert captured["preset"] == "podcast"
    # beats inside the clip window (2.0..12.0) are converted to clip-local times
    assert captured["emphasis_times"] == [0.5, 5.0]
    # podcast preset: music bed + beat-timed SFX enabled
    assert captured["music_path"] is not None
    assert captured["sfx_triggers"] is not None
    assert captured["lower_third_text"] == "Great Moment"
    assert captured["canvas"] == (1920, 1080)


@pytest.mark.asyncio
async def test_blueprint_subtitle_theme_reaches_caption_builder(monkeypatch) -> None:
    video_id = uuid7()
    clip = _clip(video_id)
    words = [
        {"text": "hello", "start": 2.5, "end": 3.0},
        {"text": "moment", "start": 3.2, "end": 4.0},
    ]
    blueprint = {
        "global_style": {
            "style_name": "Cinematic Slow",
            "subtitle_theme": {
                "colors": ["FFD700", "9E9E9E"],
                "animation": "highlight",
                "highlight_words": ["moment"],
            },
        }
    }
    service, _ = _make_service(
        monkeypatch,
        [clip],
        {"peaks": []},
        caption_engine="frames",
        words=words,
        blueprint=blueprint,
    )

    captured: dict = {}

    def fake_frames(*args, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(
        "clipforge.rendering.application.service.build_motion_caption_frames",
        fake_frames,
    )

    rendered, _ = await service.render_clips_with_captions(video_id)

    assert rendered == 1
    assert captured["accent_color"] == "FFD700"
    assert captured["muted_color"] == "9E9E9E"
    assert captured["animation"] == "glow"  # "highlight" -> glow strategy
    assert captured["theme"] == "cinematic"
    assert captured["highlight_words"] == ("moment",)
    assert captured["faces"] == ()


@pytest.mark.asyncio
async def test_render_frames_engine_builds_frame_sequence(monkeypatch) -> None:
    video_id = uuid7()
    clip = _clip(video_id)
    words = [
        {"text": "hello", "start": 2.5, "end": 3.0},
        {"text": "motion", "start": 3.2, "end": 4.0},
    ]
    service, captured = _make_service(
        monkeypatch,
        [clip],
        {"peaks": []},
        caption_engine="frames",
        words=words,
    )

    rendered, _ = await service.render_clips_with_captions(video_id)

    assert rendered == 1
    assert captured["caption_ass"] is None
    # frames render into the per-render scratch dir (deleted on completion)
    assert captured["caption_frames_dir"] is not None
    assert captured["caption_fps"] == 30


@pytest.mark.asyncio
async def test_render_music_bed_uses_detected_bpm(monkeypatch) -> None:
    video_id = uuid7()
    clip = _clip(video_id)
    service, _ = _make_service(
        monkeypatch,
        [clip],
        audio={"peaks": [5.0], "bpm": 95},
    )
    bpm_args: list = []

    def fake_music_bed(path, duration_seconds, bpm=None, volume=0.25):
        bpm_args.append(bpm)
        return Path(path)

    monkeypatch.setattr(
        "clipforge.rendering.application.service.generate_music_bed", fake_music_bed
    )

    await service.render_clips_with_captions(video_id)

    assert bpm_args == [95]


@pytest.mark.asyncio
async def test_render_skips_clip_that_is_not_ready(monkeypatch) -> None:
    video_id = uuid7()
    clip = _clip(video_id)
    object.__setattr__(clip, "status", "pending")
    service, _ = _make_service(monkeypatch, [clip], audio={"peaks": [], "bpm": None})

    rendered, _ = await service.render_clips_with_captions(video_id)

    assert rendered == 0


def test_preset_zoom_config_supports_punch_zoom() -> None:
    preset = get_preset("podcast")
    assert preset is not None
    style = RenderStyle.from_preset(preset)
    plan = ZoomEngine(style.zoom).build_zoom_plan(
        clip_duration=10.0,
        emphasis_times=[2.0, 5.0],
    )
    assert len(plan.keyframes) >= 4
    assert plan.keyframes[0].scale == 1.0
    assert any(kf.scale > 1.0 for kf in plan.keyframes)


def test_zoom_to_filter_expr_is_valid_ffmpeg_chain() -> None:
    preset = get_preset("podcast")
    assert preset is not None
    style = RenderStyle.from_preset(preset)
    plan = ZoomEngine(style.zoom).build_zoom_plan(
        clip_duration=10.0,
        emphasis_times=[2.0, 5.0],
    )
    expr = plan.to_filter_expr(1920, 1080)
    assert expr.startswith("scale=w=iw*")
    assert "eval=frame" in expr
    assert "crop=out_w=1920:out_h=1080:" in expr
    assert "exp(-0.5*" in expr
    assert ",scale=" not in expr
    # no piecewise if()/lt() form: ffmpeg cannot parse commas inside
    # filter option values, so the expression must stay comma-free
    assert "if(" not in expr
    assert "lt(" not in expr


def test_audio_plan_mutation_with_music_and_sfx() -> None:
    preset = get_preset("podcast")
    assert preset is not None
    style = RenderStyle.from_preset(preset)
    engine = AudioEngine(style.audio)
    plan = engine.build_plan(
        clip_duration=8.0,
        music_path="/tmp/bed.wav",
        sfx_triggers=[{"path": "/tmp/whoosh.wav", "time": 2.0, "volume_db": 0.0}],
    )
    assert plan.music is not None
    assert plan.music.path == "/tmp/bed.wav"
    assert len(plan.sfx) == 1


@pytest.mark.asyncio
async def test_render_merges_ai_emphasis_times_with_beats(monkeypatch) -> None:
    video_id = uuid7()
    clip = _clip(video_id)
    object.__setattr__(
        clip,
        "editing_plan_json",
        {"emphasis_times": [3.0, 11.0, 0.0], "hook_text": "AI HOOK"},
    )
    service, captured = _make_service(
        monkeypatch,
        [clip],
        audio={"peaks": [5.0], "bpm": None},
    )

    await service.render_clips_with_captions(video_id)

    # beat 5.0 -> clip-local 3.0; AI 3.0 dedupes; AI 11.0 > duration 10 -> dropped
    assert captured["emphasis_times"] == [3.0]
    assert captured["lower_third_text"] == "AI HOOK"


class FakeTimelineArtifactRepo:
    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, str], object] = {}

    async def create(self, artifact) -> object:
        self.rows[(artifact.video_id, artifact.kind)] = artifact
        return artifact

    async def get_latest(self, video_id: uuid.UUID, kind: str):
        return self.rows.get((video_id, kind))

    async def list_for_video(self, video_id: uuid.UUID) -> list:
        return [a for (v, _), a in self.rows.items() if v == video_id]

    async def delete_for_video(self, video_id: uuid.UUID) -> int:
        before = len(self.rows)
        self.rows = {}
        return before


class FakeTimelineArtifactStore:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def write(self, video_id, kind, payload, version):
        return None

    async def read_payload(self, video_id: uuid.UUID, kind: str):
        return self._payload

    async def exists(self, video_id: uuid.UUID, kind: str) -> bool:
        return self._payload is not None


@pytest.mark.asyncio
async def test_render_merges_timeline_punch_ins_with_beats(monkeypatch) -> None:
    video_id = uuid7()
    clip = _clip(video_id)  # window 2.0..12.0, duration 10
    service, captured = _make_service(
        monkeypatch,
        [clip],
        audio={"peaks": [], "bpm": None},
    )
    repo = FakeTimelineArtifactRepo()
    repo.rows[(video_id, "timeline")] = object()  # artifact index exists
    service._artifacts = repo
    service._artifact_store = FakeTimelineArtifactStore(
        {
            "punch_ins": [
                {"time": 4.0, "strength": 0.8, "reason": "beat"},   # -> 2.0
                {"time": 11.5, "strength": 0.9, "reason": "motion"},  # -> 9.5
                {"time": 14.0, "strength": 1.0, "reason": "motion"},  # outside window -> dropped
            ]
        }
    )

    await service.render_clips_with_captions(video_id)

    assert captured["emphasis_times"] == [2.0, 9.5]


@pytest.mark.asyncio
async def test_render_without_timeline_artifact_falls_back_to_beats(monkeypatch) -> None:
    video_id = uuid7()
    clip = _clip(video_id)
    service, captured = _make_service(
        monkeypatch,
        [clip],
        audio={"peaks": [5.0], "bpm": None},
    )
    service._artifacts = FakeTimelineArtifactRepo()

    await service.render_clips_with_captions(video_id)

    # no timeline artifact -> legacy beat path only
    assert captured["emphasis_times"] == [3.0]


@pytest.mark.asyncio
async def test_render_passes_emoji_and_cta_from_plan(monkeypatch) -> None:
    video_id = uuid7()
    clip = _clip(video_id)
    object.__setattr__(
        clip,
        "editing_plan_json",
        {
            "emoji_triggers": [
                {"emoji": "🔥", "time": 2.0},
                {"emoji": "💯", "time": 99.0},
                {"emoji": "", "time": 3.0},
            ],
            "cta_text": "Follow for more",
        },
    )
    service, captured = _make_service(
        monkeypatch,
        [clip],
        audio={"peaks": [], "bpm": None},
    )

    await service.render_clips_with_captions(video_id)

    assert captured["emoji_triggers"] == [{"emoji": "🔥", "time": 2.0}]
    assert captured["cta_text"] == "Follow for more"


def test_apply_style_overrides_layers_ai_directives() -> None:
    preset = get_preset("podcast")
    assert preset is not None
    base = RenderStyle.from_preset(preset)
    assert base.overlays.cta_enabled is False

    from clipforge.rendering.domain.styles import apply_style_overrides

    style = apply_style_overrides(
        base,
        {
            "caption_colors": ["FFD700", "9E9E9E", "000000"],
            "punch_zooms": True,
            "zoom_intensity": 1.0,
            "emojis_enabled": True,
            "cta_enabled": True,
            "cta_text": "Subscribe",
            "sfx_enabled": True,
            "sfx_types": ["boom", "whoosh"],
        },
    )
    assert style.caption.active_color == "FFD700"
    assert style.zoom.enabled is True
    assert style.zoom.punch_zoom_enabled is True
    assert style.zoom.emphasis_zoom_enabled is True
    assert style.zoom.punch_zoom_scale == pytest.approx(1.35)
    assert style.overlays.emojis_enabled is True
    assert style.overlays.cta_enabled is True
    assert style.overlays.cta_text == "Subscribe"
    assert style.audio.sfx_enabled is True
