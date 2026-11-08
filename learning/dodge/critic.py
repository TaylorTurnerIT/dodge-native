"""What the critic may see that the actor may not.

The engine appends hidden game state to the observation on request. Its
layout comes from the dodge_rl binding, through dodge.engine; without the
binding the names here are an empty block rather than an import failure.
"""

from .engine import CRITIC_FEATURE_COUNT, CRITIC_FEATURE_VERSION, CRITIC_GROUPS
from .observe import OBSERVATION_SIZE

WIDE_OBSERVATION_SIZE = OBSERVATION_SIZE + CRITIC_FEATURE_COUNT
CRITIC_ARCHITECTURES = ("velocity-flow-v3",)


def critic_layout():
    """The layout as a checkpoint records it: plain, picklable, comparable."""
    return {"version": CRITIC_FEATURE_VERSION, "count": CRITIC_FEATURE_COUNT,
            "groups": {name: list(span) for name, span in CRITIC_GROUPS.items()}}
