from pydantic import BaseModel


class TimelineShot(BaseModel):
    id: int
    start_time: float
    end_time: float
    duration: float
    motion_score: float
    beat_score: float
    emphasis_score: float


class TimelinePunchIn(BaseModel):
    time: float
    strength: float
    reason: str


class TimelineResponse(BaseModel):
    duration_seconds: float
    has_motion: bool
    has_audio: bool
    bpm: float | None = None
    shot_count: int
    shots: list[TimelineShot]
    cut_points: list[float]
    punch_ins: list[TimelinePunchIn]
