from clipforge.config import Settings
from clipforge.intelligence.workers.base import IntelligenceWorker
from clipforge.intelligence.workers.beat import BeatWorker
from clipforge.intelligence.workers.metadata import MetadataWorker
from clipforge.intelligence.workers.motion import MotionWorker
from clipforge.intelligence.workers.scene import SceneWorker
from clipforge.intelligence.workers.timeline import TimelineWorker


def build_workers(settings: Settings) -> dict[str, IntelligenceWorker]:
    """Build the worker registry for a process. Workers are stateless, so this
    is safe to construct once per process."""
    return {
        "metadata": MetadataWorker(),
        "scene": SceneWorker(),
        "motion": MotionWorker(),
        "beat": BeatWorker(engine=settings.beat_detector),
        "timeline": TimelineWorker(),
    }
