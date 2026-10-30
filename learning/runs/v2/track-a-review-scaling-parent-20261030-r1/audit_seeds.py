"""Read-only audit of retained Uniform2 ancestry and interrupted seed exposure."""
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
PRODUCER = BASE / ('fullgame-priority-remaining-r3-bindings-sonnet-20261027-r1/'
                   'fullgame-seed-priority-luna-20261027-r1-replica-2-uniform')
ORIGINAL = BASE / 'uniform2-continuation600-luna-20261028-r2'
RECOVERY = BASE / 'uniform2-recovery240-luna-20261028-r1'
POOL = BASE / 'rl-next-experiments-parent-20261027-r1/training-pool512-accepted.json'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stream_seed(pool, identity, slot, episode):
    payload = ['dodge_seed_priority_stream_v1', identity['study_id'], identity['replica'],
               identity['master'], slot, episode, 'uniform']
    key = hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode()).digest()
    return pool[int.from_bytes(key[:8], 'big') % len(pool)]


def statistics(starts, completed):
    start_counts = Counter(seed for _, _, _, seed in starts)
    completed_counts = Counter(seed for _, _, _, seed in completed)
    return dict(episode_starts=len(starts), completed_episodes=len(completed),
                unique_started_seeds=len(start_counts), unique_completed_seeds=len(completed_counts),
                starts_per_unique_seed=len(starts) / len(start_counts) if starts else None,
                completions_per_unique_seed=len(completed) / len(completed_counts) if completed else None,
                per_seed={str(seed): dict(starts=start_counts[seed], completed=completed_counts[seed])
                          for seed in sorted(start_counts.keys() | completed_counts.keys())})


def main():
    pool = sorted(row['seed'] for row in read(POOL)['seeds'])
    assert len(pool) == len(set(pool)) == 512
    pins = {str(POOL): sha(POOL)}
    groups = {}
    literal_starts, literal_completed = [], []
    for label, root in [('producer60', PRODUCER), ('original_prefix360', ORIGINAL),
                        ('recovery240', RECOVERY)]:
        registration = root / 'registration-final.json'
        journal = root / 'worker-output/training-events.jsonl'
        pins.update({str(f): sha(f) for f in [registration, journal]})
        reg = read(registration)
        identity = (reg['streams']['identity'] if 'streams' in reg else
                    dict(study_id=reg['study_id'], replica=reg['replica'], master=reg['vector']['seeds']['env_master_seed']))
        assert (reg.get('streams', reg)['training_pool_file_sha256']) == sha(POOL)
        segment = -1
        starts, completed = [], []
        discarded_starts, discarded_completed = [], []
        identities = set()
        segment_bases = {}
        for line in journal.open():
            row = json.loads(line)
            kind = row['kind']
            initial = kind in ('initial', 'segment_initial')
            if initial:
                segment += 1
                segment_bases[segment] = row.get('global_update_base', -1)
            discarded = label == 'original_prefix360' and segment >= 6
            if initial and kind == 'initial':
                assignments = [(v['slot'], v['seed']['episode'], v['seed']['actual_seed'])
                               for v in row['assignments']]
            elif initial:
                assignments = [(slot, episode, stream_seed(pool, identity, slot, episode))
                               for slot, episode in enumerate(row['next_episode_indices'])]
            elif kind == 'seeded_reset':
                assignments = [(v['slot'], v['seed']['episode'], v['seed']['actual_seed'])
                               for v in row['assignments']]
            elif kind == 'assignments':
                assignments = [(v['slot'], v['episode'], v['seed']) for v in row['rows']]
            else:
                assignments = []
            for slot, episode, seed in assignments:
                assert seed in pool and seed == stream_seed(pool, identity, slot, episode)
                key = (segment, slot, episode)
                assert key not in identities, (label, key)
                identities.add(key)
                entry = (segment, slot, episode, seed)
                (discarded_starts if discarded else starts).append(entry)
                # A start before update325 can remain live into the literal window;
                # only starts journaled inside325..600 are counted here.
                update = row.get('update', row.get('global_update_base', -1) + 1)
                if label != 'producer60' and not discarded and 325 <= update <= 600:
                    literal_starts.append(entry)
            if kind == 'seeded_step':
                endings = [(v['seed']['slot'], v['seed']['episode'], v['seed']['actual_seed'])
                           for v in row['completed']]
            elif kind == 'episodes_completed':
                endings = [(v['slot'], v['episode'], v['seed']) for v in row['rows']]
            else:
                endings = []
            for slot, episode, seed in endings:
                assert seed in pool and seed == stream_seed(pool, identity, slot, episode)
                entry = (segment, slot, episode, seed)
                (discarded_completed if discarded else completed).append(entry)
                if label != 'producer60' and not discarded and 325 <= row.get('update', -1) <= 600:
                    literal_completed.append(entry)
        assert len(completed) == len(set(completed)), label
        start_set = set(starts)
        assert all(entry in start_set for entry in completed), label
        groups[label] = dict(statistics(starts, completed),
                             segment_count=6 if label == 'original_prefix360' else segment + 1,
                             constructor_starts_derived_from_pinned_hash_stream=label != 'producer60',
                             _starts=starts, _completed=completed)
        if discarded_starts:
            groups['interrupted_original_after360_not_retained'] = statistics(discarded_starts, discarded_completed)
    retained_starts = [(name, *entry) for name, group in groups.items() for entry in group.get('_starts', [])]
    retained_completed = [(name, *entry) for name, group in groups.items() for entry in group.get('_completed', [])]
    combined = statistics([x[1:] for x in retained_starts], [x[1:] for x in retained_completed])
    for group in groups.values():
        group.pop('_starts', None)
        group.pop('_completed', None)
    result = dict(schema='dodge_track_a_s0_seed_audit_v1', status='completed',
                  pool_size=512, all_observed_and_derived_starts_match_exact_registered_stream=True,
                  groups=groups, retained_parent324_to_uniform2_plus_continuation600=combined,
                  literal_continuation_updates325_through600=statistics(literal_starts, literal_completed),
                  numbering='Producer is60 new updates after phase324; continuation labels0..600 reset at producer endpoint. Checkpoint420 is continuation420, cumulative852, not420 total ancestral updates. Retained post-parent324 pool training comprises60+600=660 updates; interrupted extra40 updates and update401 work are separate resource cost.',
                  limits=['Starts at fresh-environment segment constructors are derived from the pinned hash recipe and saved episode indices; reset starts and completions are directly journaled.',
                          'Completed episodes exclude abandoned live episodes; the final reset start may receive no subsequent training transition.',
                          'This audit covers this recorded learner family, not universal workspace seed nonuse or proof of overfitting.'],
                  input_pins=pins, training_executed=False, simulator_games_executed=0)
    with (HERE / 'S0-seed-audit.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: v for k, v in combined.items() if k != 'per_seed'}, sort_keys=True))


if __name__ == '__main__':
    main()
