"""Parent's independent stream-conservation check, required before the campaign's terminal audit clears its lease."""
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / 'uniform2-continuation600-sonnet-20261028-r1'
sys.path.insert(0, str(PACKAGE))
import binding as b
import seeds


def main():
    reg_path = PACKAGE / 'registration-final.json'
    reg = b.read(reg_path)
    b.validate_static(reg)
    execution = b.read(PACKAGE / 'execution-exit.json')
    b.need(execution['raw_observer_exit_code'] == 0 and execution['observer_directly_reaped'] is True,
           'successful directly-reaped observer receipt required')
    control = PACKAGE / 'dispatch' / reg['run_id']
    observation = b.read(control / 'observation.json')
    b.need(observation['observed_worker_raw_exit'] == 0 and observation['directly_reaped'] is True
           and observation['first_event'] is None and observation['owned_group_absent'] is True,
           'successful worker and cleanup required before stream audit')
    manifest = b.read(control / 'artifact-manifest.json')
    journal = Path(reg['output']) / 'training-events.jsonl'
    b.need(b.sha(journal) == manifest['training-events.jsonl'], 'training journal differs from observer manifest')
    starts = {}
    ends = {}
    assignments = {}
    with journal.open() as stream:
        for line in stream:
            b.need(line.endswith('\n'), 'torn training journal')
            row = json.loads(line)
            if row['kind'] == 'segment_initial':
                b.need(row['segment'] not in starts, 'duplicate segment start')
                starts[row['segment']] = row
            elif row['kind'] == 'segment_end':
                b.need(row['segment'] not in ends, 'duplicate segment end')
                ends[row['segment']] = row
            elif row['kind'] == 'assignments':
                index = (row['update'] - 1) // b.SEGMENT_UPDATES
                assignments.setdefault(index, []).extend(row['rows'])
    b.need(set(starts) == set(ends) == set(range(b.SEGMENTS)), 'ten complete segments required')
    modules = b.frozen()
    pool = modules['seed_priority'].validate_pool(b.read(b.POOL))
    identity = b.stream_identity(reg['parent']['expected_identity']['seed_vector'])
    checked = []
    previous = reg['parent']['initial_episode_indices']
    for index in range(b.SEGMENTS):
        start, end = starts[index], ends[index]
        b.need(start['next_episode_indices'] == previous, 'segment index chain differs')
        values, components = seeds.segment_streams(list(pool['all']), identity, previous,
                                                  frozen=modules['seed_priority'])
        digests = seeds.digests(values, components)
        b.need(digests == (start['slot_stream_sha256'], start['slot_component_sha256']),
               'independently derived stream digest differs at segment '+str(index))
        for row in assignments.get(index, []):
            slot, episode, seed = row['slot'], row['episode'], row['seed']
            b.need(0 <= slot < 64 and previous[slot] <= episode < len(values[slot])
                   and values[slot][episode] == seed and seed in pool['all']
                   and not any(lo <= seed <= hi for lo, hi in reg['exclusion_union']),
                   'returned native assignment differs from registered stream or exclusions')
        checked.append(dict(segment=index, assignments=len(assignments.get(index, [])),
                            stream_digests_verified=True, seed_exclusions_verified=True))
        previous = end['next_episode_indices']
    b.save(HERE / 'segment-stream-terminal-audit.json', dict(
        status='passed_all_ten_stream_digests_actual_assignments_and_exclusions',
        registration_sha256=b.sha(reg_path), journal_sha256=b.sha(journal), segments=checked,
        checked_before_main_lease_release=True, evaluation_outcomes_read=False))
    print('all_ten_segment_streams_independently_verified')


if __name__ == '__main__':
    main()
