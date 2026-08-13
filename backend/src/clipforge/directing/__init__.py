"""AI Video Director: turns a raw video into an executable editing blueprint.

The Director is the creative brain of the pipeline. It watches the whole video
and produces one strongly-typed `EditingBlueprint` — global style plus a
per-track timeline. The renderer never makes creative decisions; it executes
the blueprint's timeline events exactly.
"""
