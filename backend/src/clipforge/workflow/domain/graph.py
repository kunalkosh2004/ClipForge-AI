from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerSpec:
    """Declaration of one workflow node.

    `kind` is the artifact kind this worker produces (and its unique id in the
    DAG); `dependencies` are the artifact kinds that must succeed first;
    `queue` routes the node to a capability queue so heavy workers can scale
    independently.
    """

    kind: str
    queue: str = "media"
    dependencies: tuple[str, ...] = ()
    description: str = ""


WORKFLOW_GRAPH: tuple[WorkerSpec, ...] = (
    WorkerSpec(
        kind="metadata",
        queue="media",
        description="Checksum, duration, fps, codec, resolution, thumbnail.",
    ),
    WorkerSpec(
        kind="scene",
        queue="media",
        dependencies=("metadata",),
        description="Shot boundaries via PySceneDetect.",
    ),
    WorkerSpec(
        kind="motion",
        queue="media",
        dependencies=("metadata",),
        description="OpenCV optical-flow motion profile.",
    ),
    WorkerSpec(
        kind="beat",
        queue="media",
        dependencies=("metadata",),
        description="Audio energy peaks + BPM.",
    ),
    WorkerSpec(
        kind="timeline",
        queue="media",
        dependencies=("scene", "motion", "beat"),
        description="Shot emphasis + punch-in/cut timing from M1 artifacts.",
    ),
)


def specs_by_kind() -> dict[str, WorkerSpec]:
    return {spec.kind: spec for spec in WORKFLOW_GRAPH}
