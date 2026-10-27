#!/usr/bin/env python3
"""Pure stdlib: stale/failed receipt + raw exit 1 cannot satisfy frozen r3 accept_observed.
Real frozen long_d2_executor.accept_observed. No file, process, ML or native access beyond import."""
import json, sys
from pathlib import Path
FROZEN = Path(sys.argv[1] if len(sys.argv) > 1 else '/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/postovernight-long-D2-boundary-prepare-r3')
sys.dont_write_bytecode = True
sys.path.insert(0, str(FROZEN))
import long_d2_executor as e  # noqa: E402

stale_accepted = dict(schema='long_d2_outer_acceptance_v2', accepted=True, experiment_status='complete',
                      expected_exit_code=2, outcome='budget_closed_below_gate',
                      teacher_qualified=False, training_parent_eligible=False)
failed = dict(schema='long_d2_outer_acceptance_v2', accepted=False, experiment_status='failed', expected_exit_code=1)
cases = [
  ('stale accepted receipt (expected 2) + raw 1', stale_accepted, 1),
  ('stale accepted receipt (expected 2) + raw 1 + no digests', stale_accepted, 1),
  ('failed receipt + raw 0', failed, 0),
  ('failed receipt + raw 1', failed, 1),
  ('empty receipt + raw 1', {}, 1),
  ('stale accepted receipt + raw 2, digests absent (parent pins required)', stale_accepted, 2),
]
out = [dict(case=n, accepted=e.accept_observed(r, raw, 3.0)) for n, r, raw in cases]
print(json.dumps(dict(results=out), indent=2))
