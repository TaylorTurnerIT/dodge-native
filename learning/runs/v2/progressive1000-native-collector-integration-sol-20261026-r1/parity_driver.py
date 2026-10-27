"""Finite disabled-cutoff trajectories, one pinned binary per independent process."""
from pathlib import Path
import copy
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT, canonical, digest, load_native, write
import numpy as np

which = sys.argv[1]
native = load_native(which)
seeds = [[31+s+100*episode for episode in range(257)] for s in range(4)]
actions = [[((t//16)+2*s) % 9 for s in range(4)] for t in range(256)]
report = {'binary': which, 'seed_lists': seeds, 'action_vectors': actions,
          'cutoff_calls': 0, 'cases': [], 'complete': False}
try:
    for difficulty in (1, 2):
        for threads, chunk in ((1, 1), (2, 2)):
            options = dict(batch_size=4, action_repeat=4, difficulty=difficulty,
                patterns_enabled=difficulty == 2, powerups_enabled=difficulty == 2,
                raw_frame_cap=512, num_threads=threads, chunk_size=chunk,
                render_pixels=True, auxiliary_targets=True, seeds_by_slot=seeds)
            env = native.VecDodgeEnv(**options)
            initial = dict(batch_info=env.batch_info(), episode_info=env.episode_info(), observations=env.observations())
            row = {'difficulty': difficulty, 'layout': [threads, chunk], 'config': options,
                'initial_metadata': {k: v for k, v in initial.items() if k != 'observations'},
                'initial_digest': digest(initial), 'initial_observations': canonical(initial['observations']),
                'steps': [], 'ended_episodes': [], 'deaths': 0, 'caps': 0, 'resets': 0}
            report['cases'].append(row)
            rolling = hashlib.sha256(bytes.fromhex(row['initial_digest']))
            for t, vector in enumerate(actions):
                result = env.step(vector)
                assert digest(result['info']) == digest(env.episode_info())
                assert digest(result['observations']) == digest(env.observations())
                saved = digest(result)
                ended = np.flatnonzero(result['terminated'] | result['truncated']).tolist()
                for slot in ended:
                    info = copy.deepcopy(result['info'][slot])
                    assert info['seed']['actual_seed'] == seeds[slot][info['seed']['episode']]
                    assert info['seed']['slot'] == slot and info['seed']['evaluation'] is True
                    row['ended_episodes'].append({'decision': t, 'slot': slot, 'info': info})
                row['deaths'] += int(result['terminated'].sum())
                row['caps'] += int(result['truncated'].sum())
                entry = dict(decision=t, final_step_digest=saved, episode_info_digest=digest(env.episode_info()),
                             ended_slots=ended)
                if ended:
                    reset = env.reset_done(ended)
                    assert digest(result) == saved, 'reset mutated owned final step'
                    assert [r['seed']['episode'] for r in reset['info']] == [result['info'][s]['seed']['episode']+1 for s in ended]
                    for slot, info in zip(ended, reset['info'], strict=True):
                        assert info['seed']['actual_seed'] == seeds[slot][info['seed']['episode']]
                        assert not info['terminated'] and not info['truncated']
                        assert info['alive_frames'] == info['gameplay_frames'] == 0
                    entry['reset_digest'] = digest(reset)
                    row['resets'] += len(ended)
                entry['post_step_or_reset_observations_digest'] = digest(env.observations())
                entry['post_step_or_reset_batch_info_digest'] = digest(env.batch_info())
                entry['post_step_or_reset_episode_info_digest'] = digest(env.episode_info())
                rolling.update(bytes.fromhex(digest(entry)))
                row['steps'].append(entry)
                row['rolling_digest'] = rolling.hexdigest()
                if t % 32 == 0:
                    write('results/parity-' + which + '.json', report)
            row['final_metadata'] = dict(batch_info=env.batch_info(), episode_info=env.episode_info())
            row['complete'] = True
            write('results/parity-' + which + '.json', report)
            print(json.dumps({k: row[k] for k in ('difficulty', 'layout', 'rolling_digest', 'deaths', 'caps', 'resets')}), flush=True)
            del env
    report['complete'] = True
finally:
    write('results/parity-' + which + '.json', report)
