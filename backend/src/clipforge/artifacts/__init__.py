"""Artifact domain: versioned, checksummed analysis outputs.

Workers never communicate with each other directly — they read and write
artifacts. An artifact is a JSON document (plus a storage blob) identified by
`(video_id, kind)`, carrying a worker `version` so cached outputs are
invalidated when a worker changes.
"""

from clipforge.artifacts.domain.entities import Artifact
from clipforge.artifacts.domain.ports import ArtifactRepository, ArtifactStore

__all__ = ["Artifact", "ArtifactRepository", "ArtifactStore"]
