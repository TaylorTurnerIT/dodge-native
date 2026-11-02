"""Bounded fresh training lists for the accepted explicit-list native interface.

Importing or validating this module does not look up production seeds. Only an
authorized worker constructs banks. Native evaluation=True remains unchanged;
the role is training-only, not an evaluation cohort or hidden model input.
"""
import hashlib
import json
from pathlib import Path
import struct

from seed_stream import StreamSpec, seed_for


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_bound(binding):
    if sha(binding['path']) != binding['sha256']:
        raise ValueError('Fresh exclusion input changed')
    return json.loads(Path(binding['path']).read_bytes())


def specification(reg):
    lineage = reg['fresh_stream']
    registry = read_bound(lineage['registry'])
    history = read_bound(lineage['history'])['sorted_unique_seed_values']
    pool = [r['seed'] for r in read_bound(lineage['pool'])['seeds']]
    if len(history) != len(set(history)) or len(history) != 189743 or len(set(pool)) != 512:
        raise ValueError('Registered history/pool counts differ')
    spec = StreamSpec(campaign=reg['run_id'], replica=str(reg['replicas']['1']['environment_seed']),
        slots=reg['envs'], heldout_manifest_sha256=lineage['registry']['sha256'],
        additional_exclusions=tuple(map(tuple, registry['future_training_exclusion_ranges']))
            + tuple(map(tuple, reg['exclusions'])) + ((0, 1),)
            + tuple((s, s) for s in set(history) | set(pool)))
    if spec.identity != lineage['stream_identity']:
        raise ValueError('Fresh stream/exclusion identity changed')
    return spec


def bank(spec, index, episodes_per_slot):
    """Allocate a disjoint ordinal block; unused entries are never recycled.

    Each block has at least two worst-case rollouts plus one initial entry.
    No wrap, replacement, retry, wall-clock condition or native call exists.
    Tests use only small synthetic domains and never the registered spec.
    """
    if type(index) is not int or index < 0 or type(episodes_per_slot) is not int or episodes_per_slot < 1:
        raise ValueError('Invalid bank bounds')
    first = index * episodes_per_slot
    if (first + episodes_per_slot) * spec.slots > spec.capacity:
        raise ValueError('Fresh finite stream exhausted; no replacement')
    streams = [[seed_for(spec, slot, first + episode)['actual_seed']
                for episode in range(episodes_per_slot)] for slot in range(spec.slots)]
    values = [s for row in streams for s in row]
    if len(set(values)) != len(values):
        raise ValueError('Fresh bank collision; no replacement')
    digest = hashlib.sha256(b''.join(struct.pack('>I', s) for s in values)).hexdigest()
    return values, {s: 'fresh_uniform_without_replacement' for s in values}, streams, digest


def build_streams(reg, replica, index):
    if not reg['execution_authorized'] or not reg['training_authorized'] or not reg['fresh_games_authorized']:
        raise ValueError('Source preparation does not authorize fresh seed lookup')
    if replica != '1':
        raise ValueError('One learner; no replicas')
    return bank(specification(reg), index, reg['fresh_stream']['bank_episodes_per_slot'])


def audit_assignments(events, spec, episodes_per_slot):
    """Replay only consumed assignments, not bank capacity or elapsed time."""
    segment = 0
    seen = set()
    current = {}
    counts = []
    pending_native = None
    for event in events:
        if event['kind'] == 'initial_assignments':
            if pending_native is not None:
                raise ValueError('Uncommitted native reset before segment boundary')
            segment += 1
            if event['simulator_segment'] != segment:
                raise ValueError('Fresh segment order differs')
            if (event['fresh_stream_identity'] != spec.identity
                    or event['bank_episode_offset'] != (segment-1)*episodes_per_slot):
                raise ValueError('Fresh bank identity/offset differs')
            rows = event['assignments']
            if sorted(r['slot'] for r in rows) != list(range(spec.slots)):
                raise ValueError('Missing initial fresh slots')
            current = {}
            counts.append(0)
        elif event['kind'] == 'returned_reset':
            if pending_native is not None or len(event['indices']) != len(event['info']):
                raise ValueError('Uncommitted/incomplete native reset')
            pending_native = (event['indices'], [info['seed'] for info in event['info']])
            continue
        elif event['kind'] == 'seeded_reset':
            rows = event['assignments']
            slots = [r['slot'] for r in rows]
            if not segment or slots != event['indices'] or len(set(slots)) != len(slots):
                raise ValueError('Fresh reset slot identity differs')
            if pending_native != (slots, [row['seed'] for row in rows]):
                raise ValueError('Consumed assignment differs from returned native reset')
            pending_native = None
        else:
            continue
        for row in rows:
            slot = row['slot']; native = row['seed']; local = native['episode']
            if slot not in range(spec.slots) or local != current.get(slot, -1) + 1 or not 0 <= local < episodes_per_slot:
                raise ValueError('Missing/reordered fresh assignment')
            expected = seed_for(spec, slot, (segment - 1) * episodes_per_slot + local)['actual_seed']
            if (native != dict(slot=slot, episode=local, counter=0, actual_seed=expected, evaluation=True)
                    or expected in seen or row['sampling_component'] != 'uniform'):
                raise ValueError('Fresh native identity/collision differs')
            seen.add(expected); current[slot] = local; counts[-1] += 1
    if not segment or pending_native is not None:
        raise ValueError('Missing actual fresh assignments or uncommitted native reset')
    return dict(stream_sha256=spec.identity, consumed_unique_training_seeds=len(seen),
                simulator_segments=segment, assignments_per_segment=counts,
                native_seed_mode='evaluation_explicit_seed_list', role='training_only_fresh_stream')
