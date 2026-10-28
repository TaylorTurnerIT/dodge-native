"""Owned extension of the frozen uniform per-slot seed stream; stdlib only.

Same hash recipe as frozen `seed_priority._draw_key`/`sequence_entries` (uniform arm), but without the frozen
16384-entry bound: a segment of 60 updates needs `start + 15361` entries per slot, and `start` grows by the
episodes consumed by earlier segments. Draws are keyed by (study, replica, master seed, slot, episode), so the
stream continues the producer's slot streams from the saved next episode indices and never touches policy RNG.
"""
from __future__ import annotations
import hashlib
import json

STREAM_SCHEMA = 'dodge_seed_priority_stream_v1'
FROZEN_MAX_LENGTH = 16384
MAX_LENGTH = 2**21
EPISODES_PER_SEGMENT = 15361  # 60 updates x 256 decisions + the live episode
COMPONENT = 'uniform'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def stream_digest(values):
    return hashlib.sha256(canonical(values)).hexdigest()


def draw_key(study_id, replica, master, slot, episode, purpose):
    return hashlib.sha256(canonical([STREAM_SCHEMA, study_id, replica, master, slot, episode, purpose])).digest()


def uniform_stream(pool_all, *, study_id, replica, master, slot, count):
    """Seeds for episodes 0..count-1 of one slot; count may exceed the frozen bound."""
    if type(count) is not int or not 1 <= count <= MAX_LENGTH:
        raise ValueError('invalid stream length')
    if type(master) is not int or not 0 < master < 2**64 or type(slot) is not int or not 0 <= slot < 64:
        raise ValueError('invalid stream identity')
    if type(replica) is not int or replica not in (1, 2, 3) or len(pool_all) != 512:
        raise ValueError('expected the registered 512-seed pool and replica')
    width = len(pool_all)
    return [pool_all[int.from_bytes(draw_key(study_id, replica, master, slot, e, 'uniform')[:8], 'big') % width]
            for e in range(count)]


def segment_streams(pool_all, identity, starts, *, episodes=EPISODES_PER_SEGMENT, frozen=None):
    """Per-slot lists for one fresh-environment segment. `starts` are the saved next episode indices.

    When `frozen` (the pinned frozen module) is supplied and the length fits its bound, every slot is also
    derived by the frozen helper and must be identical.
    """
    if type(starts) is not list or len(starts) != 64 or any(type(s) is not int or s < 0 for s in starts):
        raise ValueError('64 saved next episode indices required')
    streams, components = [], []
    for slot, start in enumerate(starts):
        count = start+episodes
        values = uniform_stream(pool_all, slot=slot, count=count, **identity)
        if frozen is not None and count <= FROZEN_MAX_LENGTH:
            pool = dict(all=tuple(pool_all), hard=tuple(pool_all[:len(pool_all)//2]))
            reference = frozen.sequence_entries(pool, study_id=identity['study_id'], replica=identity['replica'],
                                                env_master_seed=identity['master'], arm='uniform', slot=slot, count=count)
            if [s for s, _ in reference] != values or {c for _, c in reference} != {COMPONENT}:
                raise ValueError('owned extension differs from frozen helper on slot %d' % slot)
        streams.append(values)
        components.append([COMPONENT]*count)
    return streams, components


def digests(streams, components):
    return [stream_digest(v) for v in streams], [stream_digest(c) for c in components]
