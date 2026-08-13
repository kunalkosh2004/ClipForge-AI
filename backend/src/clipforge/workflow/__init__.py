"""Workflow engine: the persisted DAG that drives artifact workers.

The workflow declares which workers exist, what artifact each depends on, and
which queue it runs on. Workers never enqueue each other — the engine advances
the DAG by enqueuing nodes whose dependencies have all produced artifacts.
"""

from clipforge.workflow.application.engine import WorkflowEngine
from clipforge.workflow.domain.entities import WorkflowNode
from clipforge.workflow.domain.graph import WORKFLOW_GRAPH, WorkerSpec
from clipforge.workflow.domain.ports import WorkflowNodeRepository

__all__ = [
    "WORKFLOW_GRAPH",
    "WorkflowEngine",
    "WorkflowNode",
    "WorkflowNodeRepository",
    "WorkerSpec",
]
