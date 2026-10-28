"""Independent saved-prefix seed audit; copied from the registered full checker and limited to six completed segments.

No evaluation scores, game simulation, checkpoint deserialization, or writes to original artifacts.
"""
from pathlib import Path
import hashlib
import json
import sys
HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'uniform2-continuation600-luna-20261028-r2'
sys.path.insert(0,str(OLD))
import binding as b
import seeds

def validate_events(reg, events, pool_all, frozen=None, episodes=seeds.EPISODES_PER_SEGMENT, completed_segments=6):
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

    expected_segments = set(range(completed_segments))
    b.need(set(starts) == set(ends) == expected_segments, 'complete saved prefix segments required')
    identity = b.stream_identity(reg['parent']['expected_identity']['seed_vector'])
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
        segment = (key[0]-1)//b.SEGMENT_UPDATES
        b.need(0 <= segment < completed_segments, 'assignment update outside registered segments')
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
    for index in range(completed_segments):
        start, end = starts[index], ends[index]
        b.need(start['next_episode_indices'] == previous, 'segment index chain differs')
        b.need(start['global_update_base'] == index*b.SEGMENT_UPDATES
               and end['global_update'] == (index+1)*b.SEGMENT_UPDATES,
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
        segment = (update-1)//b.SEGMENT_UPDATES
        b.need(0 <= segment < completed_segments, 'completed episode update outside segments')
        for row in event['rows']:
            key = (segment, row['slot'], row['episode'])
            b.need(key in assignment_map and assignment_map[key] == row['seed'],
                   'completed episode differs from its assignment')
            b.need(key not in completed_seen, 'duplicate completed slot episode')
            completed_seen.add(key)
    b.need(set(assignment_events) == set(reset_events), 'assignment/reset event coverage differs')
    return checked


def main():
    b.need(not (HERE/'original-prefix-stream-audit.json').exists(), 'Prefix audit already exists.')
    reg = b.read(OLD/'registration-final.json')
    journal = OLD/'worker-output/training-events.jsonl'
    events=[]
    for line in journal.open():
        b.need(line.endswith('\n'), 'Torn journal')
        event=json.loads(line)
        if event.get('segment',0) >= 6 or event.get('update',event.get('global_update',0)) > 360:
            continue
        events.append(event)
    modules=b.frozen()
    pool=modules['seed_priority'].validate_pool(b.read(b.POOL))
    checked=validate_events(reg,events,list(pool['all']),modules['seed_priority'])
    b.need(len(checked)==6, 'Six saved segments required')
    b.save(HERE/'original-prefix-stream-audit.json',dict(
        schema='uniform2_recovery240_original_prefix_stream_v1', status='passed_complete_saved_prefix_through360',
        completed_segments=6,completed_updates=360,segments=checked,
        original_registration_sha256=b.sha(OLD/'registration-final.json'),
        journal_sha256=b.sha(journal),source_sha256=b.sha(Path(__file__)),
        incident_audit_sha256=b.sha(HERE/'incident-audit.json'),evaluation_outcomes_read=False,
        limit='Only the durable six-segment prefix is qualified; later interrupted work remains unqualified.'))
    print('saved_prefix360_streams_assignments_and_seed_exclusions_verified')

if __name__=='__main__':
    main()
