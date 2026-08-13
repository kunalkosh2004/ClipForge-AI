"""Intelligence workers: one detector per artifact kind.

Workers read artifacts (`input_artifacts`) and produce one artifact. They are
stateless (except immutable model weights/deps), so they scale horizontally;
the workflow engine drives them, never the workers themselves.
"""

from clipforge.intelligence.workers.base import IntelligenceWorker
from clipforge.intelligence.workers.beat import BeatWorker
from clipforge.intelligence.workers.metadata import MetadataWorker
from clipforge.intelligence.workers.motion import MotionWorker
from clipforge.intelligence.workers.scene import SceneWorker

__all__ = [
    "BeatWorker",
    "IntelligenceWorker",
    "MetadataWorker",
    "MotionWorker",
    "SceneWorker",
]
