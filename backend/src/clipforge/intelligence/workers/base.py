from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar


class IntelligenceWorker(ABC):
    """Contract for a single-responsibility artifact producer.

    Subclasses declare their `kind` (the artifact they produce and their node
    in the workflow DAG), a `version` (bumped whenever the detector changes,
    which invalidates cached artifacts), and the artifact kinds they consume
    (`input_artifacts`). `detect` must be a pure function of the source file
    and its dependency artifacts — no side effects, no shared state.
    """

    kind: ClassVar[str]
    version: ClassVar[str]
    input_artifacts: ClassVar[tuple[str, ...]] = ()
    # False for pure-artifact workers (e.g. timeline) so the pipeline skips
    # downloading the source video just to feed a JSON-only computation.
    needs_source: ClassVar[bool] = True

    @abstractmethod
    async def detect(
        self, source_path: Path | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute the artifact payload.

        `source_path` is the downloaded source video (None when
        `needs_source` is False). `params` carries the payloads of
        `input_artifacts` under `params["artifacts"][kind]` (None when
        missing). Must be JSON-serializable.
        """

    def validate(self, payload: dict[str, Any]) -> None:
        """Reject invalid output before it is persisted. Raises ValueError."""
        if not isinstance(payload, dict):
            raise ValueError(f"{self.kind} worker must return a dict")
