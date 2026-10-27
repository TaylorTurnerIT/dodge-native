# D2 continuation terminal evidence review (read-only)

Run: `D2-continuation-20261025-r1`
Scope: terminal evidence only. No training, eval, relaunch, lease change, PR, commit, or edits outside this folder.

## Verdict

**No blocking findings.** Two low-severity documentation/accounting findings and one scoping correction (below). The run's evidence is internally consistent on every checked item.

## Findings

### F1 (low): `direct_runtime_pyc_files: []` conflicts with `__pycache__` in the launch directory

- Path: `learning/runs/v2/d2-continuation-prepare-luna-20261025-r3/__pycache__/` (contains `runner.cpython-312.pyc`, `execute_once.cpython-312.pyc`, `test_outputs.cpython-312.pyc`, `test_launcher_lifecycle.cpython-312.pyc`; mtime 16:46, before launch at 16:57:48).
- Acceptance record: `learning/runs/v2/d2-continuation-parent-prepare-20261025-r1/parent-acceptance-r1.json` reports `"direct_runtime_pyc_files": []`, and finding F4 says no direct `.pyc` exists in the isolated runtime package before launch.
- Trigger: the worker runs `runner.py` from `d2-continuation-prepare-luna-20261025-r3/`, the same directory that holds the `__pycache__`.
- Consequence: the literal "no direct runtime pyc" statement is false for this directory as written. Scope the claim. Mitigating facts: launch used `-B` and an empty `PYTHONPYCACHEPREFIX` (`empty-pycache-prefix`, empty before and after), which redirects bytecode lookup away from in-tree `__pycache__`. Observer `events` and `cleanup_signals` are empty. F4 partly discloses retained `__pycache__` artifacts, so this is a wording/scope issue, not an execution failure.

### F2 (low, accounting): 57644 final-abandoned frames have no journal row

- Path: `learning/runs/v2/D2-continuation-20261025-r1/training-episodes.jsonl`.
- Checked: `completed` rows = 3506, `gameplay_frames` sum = 3869148. `abandoned_parent_episode` rows = 64, sum = 42768 (parent-inherited, distinct from current training). `reset` = 3140 (gameplay 0), `initial` = 1. No current-run abandoned or final-in-progress row exists.
- Counter: `worker-result.json` `counters.raw_frames` = 3926792. 3926792 − 3869148 = **57644**, which closes arithmetically but is only derivable by subtraction. The journal does not record it.
- Consequence: frame accounting closes, but the 57644 frames are not individually auditable. No code failure.

### F3 (correction, not a defect): parent abandoned frames are 42768, not 0

- The child summary's "0 frames" for the 64 parent abandoned episodes is wrong. `sum(row['info']['gameplay_frames'])` over those rows = **42768**. Correct the prose; the journal is correct.

## Checks passed

Hashes (all re-computed):
- `artifact-manifest.json`: all 16 listed files match their recorded SHA-256.
- Final candidate `checkpoint-000132-candidate.pt` = `bf858ed9975e6f994acbca011895b140be6943cf1852c88b54549a9c8db0c1a8`. Matches manifest, `checkpoint-000132-candidate.pt.json`, and `development-000132.json`.
- Registration `registration-r1.json` = `bf425a502987b51b4e637cbe750eee652ce359baa07e229af84f291da3e931ed`. Differs from the final candidate hash.
- Parent receipt `d2-training-v3-parent-terminal-audit-20261025-r1/parent-terminal-receipt.json` hashes to `533235fd4c3b808c3be84e97e84485d74933e3a55edaf21c62301ca20ac47255`.
- Parent checkpoint `2e13b46edad5b2790cec52b47d33b643cbd6846387994c24fe14d5d36f0521a2` matches the registration lease.

Execution:
- Exactly one outer and one worker launch (`actual_worker_launch_count` 1, `launch_count` 1, `launch-marker.json` `single_use` true). Raw exit 0 for both. Worker and group absent. No cancel file, no cleanup signals, no publication failure.
- Inclusive observed wall `1034.278296417091` s ≤ 1800. Work `1030.53735958` s < 1600.
- Peaks: aggregate RSS `1010745344` (max over 990 samples) < 6442450944. Worker RSS `966508544`. MPS driver `2456387584` < 6 GiB.
- Cache prefix empty before and after (`cache_empty_before`, `cache_prefix_empty_after`).

Training and eval:
- `training-metrics.jsonl`: 60 rows, `phase_update` 73..132, `local_update` 1..60. Final counters match worker-result.
- Cumulative: inherited raw frames 7849317 + current 3926792 = 11776109 ✓. Inherited updates 120 + 60 = 180 ✓. Inherited optimizer steps 15264 + 7520 = 22784 ✓.
- Wall, full outer: 1188.34122675 + 1034.278296417091 = **2222.619523167091** (use this for the future parent receipt). The worker's `2218.8785863` is provisional work-only time (1188.34122675 + 1030.53735958) and is not the total.
- Eval sentry 72 and final 132: both 64 seeds, identical seed set.
- Quartiles at update 132 (alive frames): Q1 (bottom 16) mean 565.8125, Q4 (top 16) mean 2786.25, overall mean 1518.75. Min 413, max 4332. Recomputed from rows; matches.
- Deaths at 132: normal 34, kamikaze_enemy 12, static 11, moving 5, kamikaze_explosion 2 = 64. Unknown/unavailable 0.
- Competence: `competence_passed` false; 1518.75 < 3060. No promotion, `training_eligible` false, `promoted` false.
- Evidence files consistent with `worker-result.json`: `raw_frames` 75460 (update 72) and 97264 (update 132) equal sum of per-episode `gameplay_frames`.

Seeds:
- Next seed indices = current + 1 for all 64 slots (verified against `final_resume_next_episode_indices`).
- Initial indices of this run equal the prior D2 run's `final_resume_next_episode_indices` exactly.
- `run_seed` 810631976 is unchanged from the prior run (continuation of the stream, not fresh).

Observer:
- `observation.json`: `success_authoritative` true, `outer_raw_exit` 0, `worker_exit_accepted` true, `lease_still_exact` true, `candidate_sha256` matches the final candidate hash.

## Coverage limits

- Reviewed only the listed artifacts and the parent-terminal receipt located by hash. Did not re-execute the runner, re-derive policy behavior, or inspect `resources.jsonl` beyond max-RSS and process identity fields.
- Did not verify the contents of the frozen Haiku review (`d2-continuation-frozen-review-haiku-20261025-r1`); it is cited only for context.
- F1 is a file-presence check; I did not check whether the 16:46 `.pyc` files match current sources byte-for-byte, because the launch's empty `PYTHONPYCACHEPREFIX` makes that irrelevant to execution.
- Quartile means come from the 64 rows in `development-000132.jsonl`; I did not recompute the eval itself.
