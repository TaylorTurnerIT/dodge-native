"""Paired deterministic, uniform512 per-slot streams; no policy RNG use."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import binding as b

STREAM_SCHEMA = 'one_frame_training_comparison_paired_pool_stream_v1'
SLOTS = 64
POOL_SIZE = 512


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_pool(doc):
    b.need(type(doc) is dict and doc.get('schema') == 'dodge_seed_priority_pool_v1'
           and doc.get('role') == 'training_only'
           and doc.get('evaluation_seeds_used_for_selection') is False
           and doc.get('history_closure') == 'parent_accepted_bounded_scope_no_universal_claim',
           'accepted training-only seed pool required')
    rows = doc.get('seeds')
    b.need(type(rows) is list and len(rows) == POOL_SIZE, 'uniform512 pool required')
    original_exclusions = doc.get('excluded_seed_ranges')
    b.need(type(original_exclusions) is list and bool(original_exclusions), 'pool exclusion history missing')
    seeds, strata = [], {}
    for row in rows:
        b.need(type(row) is dict and set(row) == {'seed', 'stratum', 'training_evidence'},
               'training pool row schema differs')
        seed = row['seed']
        evidence = row['training_evidence']
        b.need(type(seed) is int and 0 <= seed <= 0xffffffff and seed not in strata,
               'pool seed is duplicated or outside uint32')
        b.need(row['stratum'] in ('hard', 'easy') and type(evidence) is dict
               and evidence.get('evaluation') is False and evidence.get('role') == 'training',
               'pool seed is not training-only')
        for interval in original_exclusions:
            b.need(type(interval) is list and len(interval) == 2 and all(type(x) is int for x in interval)
                   and interval[0] <= interval[1], 'pool exclusion range malformed')
            b.need(not interval[0] <= seed <= interval[1], 'pool overlaps its registered exclusions')
        seeds.append(seed)
        strata[seed] = row['stratum']
    b.need(len(set(seeds)) == POOL_SIZE and list(strata.values()).count('hard') == POOL_SIZE//2
           and list(strata.values()).count('easy') == POOL_SIZE//2, 'pool must be unique and balanced')
    return dict(all=tuple(sorted(seeds)), strata=strata,
                pool_sha256=hashlib.sha256(canonical(doc)).hexdigest(),
                source_exclusions=original_exclusions)


def frame_stream_capacity(frame_target, *, slots=SLOTS):
    b.need(type(frame_target) is int and frame_target > 0 and slots == SLOTS,
           'registered frame target and 64 slots required')
    # Every action repeat setting returns at least one gameplay frame per live slot-decision.
    # The ceiling bounds calls including the target-crossing call; add one initial episode seed.
    return (frame_target + slots - 1)//slots + 1


def stream_seed(pool, pair_seed, slot, episode):
    b.need(type(pair_seed) is int and 0 < pair_seed < 2**64
           and type(slot) is int and 0 <= slot < SLOTS
           and type(episode) is int and episode >= 0, 'paired stream identity differs')
    key = hashlib.sha256(canonical([STREAM_SCHEMA, pair_seed, slot, episode, 'uniform'])).digest()
    return pool['all'][int.from_bytes(key[:8], 'big') % len(pool['all'])]


def materialize(pool, pair_seed, capacity):
    b.need(type(capacity) is int and capacity >= 2, 'stream capacity invalid')
    seeds_by_slot, components_by_slot, digests = [], [], []
    for slot in range(SLOTS):
        seeds = [stream_seed(pool, pair_seed, slot, episode) for episode in range(capacity)]
        components = ['uniform']*capacity
        seeds_by_slot.append(seeds)
        components_by_slot.append(components)
        digests.append(dict(slot=slot, seeds_sha256=digest(seeds), components_sha256=digest(components)))
    return seeds_by_slot, components_by_slot, digests


def verify_exclusions(pool, excluded_ranges):
    b.need(type(excluded_ranges) is list, 'registered exclusion union required')
    for low, high in excluded_ranges:
        b.need(type(low) is int and type(high) is int and 0 <= low <= high <= 0xffffffff,
               'registered uint32 exclusion range malformed')
    b.need(not any(low <= seed <= high for seed in pool['all'] for low, high in excluded_ranges),
           'uniform training pool overlaps a reserved evaluation range')


def validate_registered_streams(reg):
    doc = b.read(b.TRAINING_POOL)
    pool = validate_pool(doc)
    b.need(b.sha(b.TRAINING_POOL) == reg['streams']['training_pool_file_sha256']
           and pool['pool_sha256'] == reg['streams']['training_pool_sha256'], 'training pool pin differs')
    verify_exclusions(pool, reg['exclusion_union'])
    capacity = frame_stream_capacity(reg['gameplay_frame_target_per_arm'])
    b.need(reg['streams']['capacity_per_slot'] == capacity
           and reg['streams']['initial_episode_indices'] == [0]*SLOTS,
           'paired stream capacity/continuation differs')
    _, _, digests = materialize(pool, reg['training_pair_seed'], capacity)
    b.need(digests == reg['streams']['slot_stream_digests'], 'registered paired stream digests differ')
    return pool


def build_registered_streams(reg):
    pool = validate_pool(b.read(b.TRAINING_POOL))
    verify_exclusions(pool, reg['exclusion_union'])
    capacity = frame_stream_capacity(reg['gameplay_frame_target_per_arm'])
    seeds, components, digests = materialize(pool, reg['training_pair_seed'], capacity)
    b.need(capacity == reg['streams']['capacity_per_slot']
           and digests == reg['streams']['slot_stream_digests'], 'paired streams differ from registration')
    return pool, seeds, components
