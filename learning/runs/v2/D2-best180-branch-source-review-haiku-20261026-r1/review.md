# BEST180 branch source review (read-only, frozen source)

Target: `learning/runs/v2/D2-best180-branch-prepare-luna-20261026-r1/` (source-freeze.json, 19 source hashes verified).
Scope: source mechanics only. No registration, lease, launch, training, games, gradients, or checkpoint edits.
Verdict: **conditional**. Two material findings should be fixed before the parent refreshes pins. Three low findings are optional.

## Findings

### 1. Hardcoded evidence count misreports seven evaluations (medium)

`execute_once.py:208` returns `"evaluations_checked": 2`, but the loop at `execute_once.py:134` validates all seven `r.EVALUATION_UPDATES` certificates (180 to 252, step 12). The value lands in `execution-result.json` under `evidence_checks`, so the audit record says two when seven were checked. No test asserts this field (grep of the test files finds no `evaluations_checked`).

Fix: `"evaluations_checked": len(r.EVALUATION_UPDATES)`, and add an assertion in `test_outputs.py`.

### 2. Intermediate candidate checkpoints 192 to 240 are not state-validated (medium)

For updates 192, 204, 216, 228, and 240, `execute_once.py:156-162` checks only the file path, file hash, and sidecar flags. The embedded state checks (`execute_once.py:168-194`: schema, registration/config/policy/runtime/native hashes, `phase_update`, `local_update`, `counters`, `inherited_counters`, `cumulative_counters`, `next_episode_indices`, abandoned records, `update_progress`) run only on the final 252 checkpoint.

Failure scenario: `runner.py:623-652` stamps each mid-candidate with `phase_update`, `local_update`, and `cumulative_counters = parent_228 + local`. If any of those fields is wrong in an intermediate checkpoint (for example a stale counter, wrong `local_update`, or a missing `parent_checkpoint_sha256`), validation still passes. That checkpoint then enters the parent candidate audit, which selects BEST by mean alive frames. The brief's specific risk (local phase 180 base, cumulative base 228) is therefore enforced only at the endpoint.

Fix: inside the per-update loop, load each checkpoint with `ckpt.load_checkpoint(path, expected_sha256=certificate["checkpoint_sha256"])` and require:
- `phase_update == update` and `local_update == update - 180`;
- `counters == metrics[local-1]["counters"]`;
- `cumulative_counters == continuation_cumulative_counters(parent_228, counters)`;
- the identity, registration, config, policy, runtime, native, and parent hashes match the final checkpoint;
- `update_progress["complete"] is True` and 64 abandoned records.

### 3. Competence predicate checked only on the final certificate (low)

`execute_once.py:206` compares `competence_passed` against `mean_alive_frames >= 3060` using the last loop value only. Intermediate `competence_passed` values are unchecked. This does not affect selection, since selection uses the mean alive frames, and the brief excludes competence promotion. Fix: move the check into the loop.

### 4. Launcher validates with sibling `runner` but worker runs `reg["runner_path"]` (low)

`execute_once.py:17` does `import runner as r`, which resolves to the file beside the launcher. The worker is started from `reg["runner_path"]` (`execute_once.py:250`). Nothing asserts they are the same file. If a registration pointed `runner_path` at a different copy, the launcher's validators and the worker's code would diverge. Fix: in `execute()` after `load_registration`, add `r.need(Path(r.__file__).resolve() == Path(reg["runner_path"]).resolve(), "Launcher validator origin differs")`.

### 5. Fragile loop-variable reuse in output validation (low)

`execute_once.py:170` and `:206` use `certificate` and `evaluation` from the last loop iteration. This is correct only because `EVALUATION_UPDATES` ends at 252. Fix: read `development-000252.json` explicitly.

## Checked and found correct

- Evaluation schedule: `runner.py:38` gives 180 to 252 step 12. The trigger `runner.py:699-700` (`PHASE_START + update in EVALUATION_UPDATES[1:]`) fires at local 12 to 72. The entry evaluation at `runner.py:670` runs before training.
- Cumulative counters: `runner.py:304-316` composes parent 228 with local work. `execute_once.py:193-194` requires 300 at the end.
- Seed `3791628417` is `0xE1FFA881`. It is outside the excluded ranges (`runner.py:119-120`).
- Restore ordering: model, Adam, and RNG are fingerprinted before env construction (`runner.py:582-596`), and the restore is exact against the parent.
- Frame conservation: `ppo.py:327-328` makes `gameplay_frames` cumulative raw frames per episode. Completed plus final-abandoned `gameplay_frames` therefore equals `counters.raw_frames` by construction, with no overcount. Parent abandoned episodes are recorded and excluded (`execute_once.py:122-129`).
- Episode index contract: `checkpoints.py:57-68` requires `next == current + 1`, and the journal validator at `runner.py:514-546` is consistent with it.
- Inference isolation: `dev_eval.py:109` uses `@torch.no_grad`, `dev_eval.py:167` restores train mode, and `runner.py:625-659` checks before/after fingerprints of model, Adam, RNG, and env.
- Budget: prior development certificate `development-000180.json` records `elapsed_seconds` 6.04. Five extra evaluations add roughly 30 s to the 1169.7 s measured for the prior 72-update run. This is an estimate, not a measured full run.
- Lifecycle: the launcher's signal, cleanup, and publication-failure paths (`execute_once.py:214-354`) have no defect that I could find by reading.
- `state.json` (authoritative): `active_long_campaign` is `None`, consistent with the lease being null. No lease keys exist in it.
- `docs/implementation-plan-v2.md` and `docs/SPEC_PRIVILEGED_VIT_RL.md` have no direct references to BEST180 or the 3060 threshold. I did not audit them further.

## Scope and limits

- This is source review only. It is not runtime evidence. The 23 contract tests use synthetic fixtures and do not run the real worker.
- Hashes of the frozen `runner.py` and `execute_once.py` match `source-freeze.json`.
- The live registration, pins, and lease are parent-owned and were not inspected here. This review does not read the partially written Luna registration.
- The parent-accepted 180 checkpoint and receipt were not re-hashed here. The parent validates them.
