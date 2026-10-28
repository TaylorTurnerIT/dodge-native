"""Independent terminal stream and assignment-conservation check for recovery240 r1."""
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
PACKAGE = HERE
sys.path.insert(0, str(PACKAGE))
import binding as b
import seeds


def read_journal(path):
    rows = []
    with Path(path).open() as stream:
        for line_number, line in enumerate(stream, 1):
            b.need(line.endswith('\n'), 'torn training journal at line '+str(line_number))
            rows.append(json.loads(line))
    return rows


def validate_events(reg, events, pool_all, frozen=None, episodes=seeds.EPISODES_PER_SEGMENT):
    starts, ends = {}, {}
    assignment_events, reset_events, completed_events = {}, {}, {}
    for row in events:
        kind = row.get('kind')
        if kind == 'segment_initial':
            segment = row['segment']
            b.need(segment not in starts, 'duplicate segment start')
            starts[segment] = row
        elif kind == 'segment_end':
            segment = row['segment']
            b.need(segment not in ends, 'duplicate segment end')
            ends[segment] = row
        elif kind in ('assignments', 'returned_reset'):
            key = (row['update'], row['decision'])
            target = assignment_events if kind == 'assignments' else reset_events
            b.need(key not in target, 'duplicate '+kind+' event')
            target[key] = row
        elif kind == 'episodes_completed':
            key = (row['update'], row['decision'])
            b.need(key not in completed_events, 'duplicate episodes_completed event')
            completed_events[key] = row

    expected_segments = set(range(b.SEGMENTS))
    b.need(set(starts) == set(ends) == expected_segments, 'four complete recovery segments required')
    identity = b.stream_identity(b.read(b.RESTORE_REG)['original_seed_vector'])
    previous = list(reg['parent']['initial_episode_indices'])
    b.need(len(previous) == b.SLOTS and all(type(x) is int and x >= 0 for x in previous),
           '64 qualified initial episode indices required')
    assignment_rows_by_segment = {i: [] for i in expected_segments}
    reset_count_by_segment = {i: 0 for i in expected_segments}
    seen_assignments = set()
    for key in sorted(set(assignment_events) | set(reset_events)):
        b.need(key in assignment_events and key in reset_events,
               'seed assignment and returned reset are not paired at '+repr(key))
        assignment, reset = assignment_events[key], reset_events[key]
        rows = assignment['rows']
        slots = reset['slots']
        b.need(type(rows) is list and rows and type(slots) is list and slots
               and all(type(s) is int and 0 <= s < b.SLOTS for s in slots)
               and len(slots) == len(set(slots)), 'invalid reset/assignment slot list at '+repr(key))
        b.need(type(reset['startup_frames']) is int and reset['startup_frames'] == b.STARTUP*len(slots),
               'returned reset startup count differs at '+repr(key))
        row_slots = [r.get('slot') for r in rows]
        b.need(len(row_slots) == len(set(row_slots)) and set(row_slots) == set(slots),
               'reset slots and seed assignment rows differ at '+repr(key))
        segment = (key[0]-b.CAMPAIGN_BASE-1)//b.SEGMENT_UPDATES
        b.need(0 <= segment < b.SEGMENTS, 'assignment update outside registered segments')
        reset_count_by_segment[segment] += len(slots)
        for item in rows:
            slot, episode, seed = item.get('slot'), item.get('episode'), item.get('seed')
            b.need(type(slot) is int and 0 <= slot < b.SLOTS and type(episode) is int and type(seed) is int,
                   'invalid seed assignment row')
            unique = (segment, slot, episode)
            b.need(unique not in seen_assignments, 'duplicate slot episode assignment '+repr(unique))
            seen_assignments.add(unique)
            assignment_rows_by_segment[segment].append((slot, episode, seed))

    checked = []
    constructor_assignments = {}
    for index in range(b.SEGMENTS):
        start, end = starts[index], ends[index]
        b.need(start['next_episode_indices'] == previous, 'segment index chain differs')
        b.need(start['global_update_base'] == b.CAMPAIGN_BASE+index*b.SEGMENT_UPDATES
               and end['global_update'] == b.CAMPAIGN_BASE+(index+1)*b.SEGMENT_UPDATES,
               'segment update boundary differs')
        next_indices = end['next_episode_indices']
        b.need(type(next_indices) is list and len(next_indices) == b.SLOTS
               and all(type(x) is int and x >= previous[s] for s, x in enumerate(next_indices)),
               'invalid ending episode indices')
        values, components = seeds.segment_streams(list(pool_all), identity, previous,
                                                    episodes=episodes, frozen=frozen)
        b.need(start['slot_stream_sha256'] == seeds.digests(values, components)[0]
               and start['slot_component_sha256'] == seeds.digests(values, components)[1],
               'independently derived stream digest differs at segment '+str(index))
        initial_constructor_seeds = [values[slot][previous[slot]] for slot in range(b.SLOTS)]
        by_slot = {slot: [] for slot in range(b.SLOTS)}
        for slot, episode, seed in assignment_rows_by_segment[index]:
            b.need(previous[slot]+1 <= episode < next_indices[slot],
                   'assignment outside expected reset episode range')
            b.need(episode < len(values[slot]) and values[slot][episode] == seed
                   and seed in pool_all
                   and not any(lo <= seed <= hi for lo, hi in reg['exclusion_union']),
                   'assignment seed differs from stream or intersects exclusions')
            by_slot[slot].append(episode)
        for slot in range(b.SLOTS):
            expected = list(range(previous[slot]+1, next_indices[slot]))
            actual = by_slot[slot]
            b.need(sorted(actual) == expected and len(actual) == len(set(actual)),
                   'incomplete or extra assignments for segment %d slot %d' % (index, slot))
            # Constructor episode is previous[slot]; its seed is fixed by the stream and is not a reset row.
            initial_seed = values[slot][previous[slot]]
            b.need(initial_seed in pool_all
                   and not any(lo <= initial_seed <= hi for lo, hi in reg['exclusion_union']),
                   'initial constructor assignment is outside the registered pool or intersects exclusions')
            constructor_assignments[(index, slot, previous[slot])] = initial_seed
        segment_resets = sum(next_indices[s]-previous[s]-1 for s in range(b.SLOTS))
        b.need(reset_count_by_segment[index] == segment_resets,
               'returned reset count differs from complete assignment coverage')
        previous = next_indices
        checked.append(dict(segment=index, resets=segment_resets,
                            assignments=sum(len(by_slot[s]) for s in range(b.SLOTS)),
                            initial_constructor_seed_sha256=seeds.stream_digest(initial_constructor_seeds),
                            initial_constructor_assignments_derived=True, stream_digests_verified=True,
                            complete_slot_episode_coverage=True, seed_exclusions_verified=True))

    # Every completed episode must refer to one unique assignment with the same seed.
    assignment_map = dict(constructor_assignments)
    assignment_map.update({(seg, slot, episode): seed for seg, rows in assignment_rows_by_segment.items()
                           for slot, episode, seed in rows})
    completed_seen = set()
    for (update, _decision), event in completed_events.items():
        segment = (update-b.CAMPAIGN_BASE-1)//b.SEGMENT_UPDATES
        b.need(0 <= segment < b.SEGMENTS, 'completed episode update outside segments')
        for row in event['rows']:
            key = (segment, row['slot'], row['episode'])
            b.need(key in assignment_map and assignment_map[key] == row['seed'],
                   'completed episode differs from its assignment')
            b.need(key not in completed_seen, 'duplicate completed slot episode')
            completed_seen.add(key)
    b.need(set(assignment_events) == set(reset_events), 'assignment/reset event coverage differs')
    return checked


def main():
    reg_path = PACKAGE/'registration-final.json'
    reg = b.read(reg_path)
    b.validate_static(reg)
    checker_sha = b.sha(Path(__file__))
    b.need(reg['input_pins'].get(str(Path(__file__).resolve())) == checker_sha,
           'registered parent stream checker source pin differs')
    execution = b.read(PACKAGE/'execution-exit.json')
    b.need(execution['raw_observer_exit_code'] == 0 and execution['observer_directly_reaped'] is True,
           'successful directly-reaped observer receipt required')
    control = PACKAGE/'dispatch'/reg['run_id']
    observation = b.read(control/'observation.json')
    b.need(observation['observed_worker_raw_exit'] == 0 and observation['directly_reaped'] is True
           and observation['first_event'] is None and observation['owned_group_absent'] is True,
           'successful worker and cleanup required before stream audit')
    manifest = b.read(control/'artifact-manifest.json')
    journal = Path(reg['output'])/'training-events.jsonl'
    journal_sha = b.sha(journal)
    b.need(journal_sha == manifest['training-events.jsonl'], 'training journal differs from observer manifest')
    modules = b.frozen()
    pool = modules['seed_priority'].validate_pool(b.read(b.POOL))
    checked = validate_events(reg, read_journal(journal), list(pool['all']), modules['seed_priority'])
    b.save(HERE/'segment-stream-terminal-audit.json', dict(
        schema='uniform2_recovery240_stream_audit_v1',
        status='passed_all_four_stream_digests_complete_assignments_and_exclusions',
        registration_sha256=b.sha(reg_path), journal_sha256=journal_sha,
        checker_sha256=checker_sha, segments=checked, checked_before_main_lease_release=True,
        evaluation_outcomes_read=False))
    print('all_four_recovery_segment_streams_and_assignments_independently_verified')


if __name__ == '__main__':
    main()
