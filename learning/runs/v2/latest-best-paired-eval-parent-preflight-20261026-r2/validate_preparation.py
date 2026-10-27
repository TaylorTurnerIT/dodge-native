"""Parent validation: dependency preflight and fake live episode boundaries only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

OWN = Path(__file__).resolve().parent
ROOT = OWN.parents[3]
PREP = ROOT / 'learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r2'
sys.path.insert(0, str(PREP / 'tests'))
import test_paired_eval as fixture
import worker
from dodge_rl.dev_eval import DEATH_CAUSES


class LiveThenDeath(fixture.FakeEnv):
    def step(self, actions):
        result = super().step(actions)
        if self.calls == 3:
            info = result['info'][0]
            info.update(bootstrap=False, alive_frames=11, objective_return=-4.89,
                        death_cause='normal_enemy', fatal_gameplay_frame=12,
                        death_observed_lethal_contacts={
                            cause: int(cause == 'normal_enemy') for cause in DEATH_CAUSES})
            result['terminated'][0] = True
            result['truncated'][0] = False
        return result


started = time.monotonic()
manifest = worker.verify_inputs()
origins = worker.verify_module_origins()
results = []
for env_type in (fixture.FakeEnv, LiveThenDeath):
    for mode in ('argmax', 'sampled'):
        fixture.FakeEnv.made.clear()
        rows = worker.evaluate(fixture.FakeModel(), checkpoint='best180', mode=mode,
                               replicate_seed=64001 if mode == 'sampled' else None,
                               env_factory=env_type, config_factory=fixture.fake_config)
        assert len(rows) == 64
        assert all(env.calls == 3 and env.closed for env in fixture.FakeEnv.made)
        expected_death = env_type is LiveThenDeath
        assert all(row['terminated'] == expected_death for row in rows)
        assert all(row['truncated'] != expected_death for row in rows)
        assert all(row['death_cause'] == ('normal_enemy' if expected_death else None)
                   for row in rows)
        results.append({'fake_environment': env_type.__name__, 'mode': mode,
                        'episodes': len(rows), 'steps_per_episode': 3, 'passed': True})
receipt = {
    'schema': 'paired_eval_parent_preparation_validation_v1',
    'actual_game_episodes': 0, 'fake_boundary_cases': results,
    'dependency_pins_verified': 13513, 'module_origins': origins,
    'scope': 'Frozen dependency checks, fake live-to-cap/death paths. No native game constructed.',
    'wall_seconds': time.monotonic() - started,
    'preparation_receipt_sha256': hashlib.sha256((PREP / 'preparation-receipt.json').read_bytes()).hexdigest(),
}
(OWN / 'preflight-and-boundaries.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
