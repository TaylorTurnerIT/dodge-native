# LR schedule draft r2 results

Implemented CPU-only helper in this successor directory. r1 and Haiku review remain untouched.

## Changes

- Each application requires actual completed cumulative updates and checks `completed_schedule_updates == actual_cumulative_updates - 372`.
- Fresh metadata creation requires actual cumulative count exactly 372. Resume requires every metadata key; no missing-field fallback.
- Completed count remains uncapped after update 432. Later updates hold `1e-5`.
- Validation rejects stale counts, reset/missing/invalid fields, bool/float integers, spec mismatch, and group-count mismatch before mutation. All group LRs validate before any group changes.
- Returned progress is staged proposal. Caller must commit it only after successful `ppo_update`.
- Manifest binds canonical spec declaration hash and exact helper source hash. Formula executes as code; no unsafe evaluation.
- Integration design now points to selected-324 runner and documents future successor requirements. It confirms current run remains fixed `3e-5`.

## CPU synthetic verification

Command: `PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH unset /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -m unittest -v`

Working directory: `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/LR-schedule-draft-luna-20261026-r2`. Interpreter: `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python` (CPython 3.12). Raw final exit: `0`. Seven tests pass. `test.log` retains the first failed fixture run (raw exit 1) and corrected rerun (raw exit 0).

Coverage: full 60-update sequence; 61st and resumed post-horizon hold; actual cumulative mismatch; wrong fresh parent; missing/invalid metadata; atomic nonfinite group rejection; exact synthetic Adam split/resume including per-group LRs; unchanged moments/steps; manifest verification.

## Pins and limits

- Frozen r1 source pin reverified: `24729b8efb9f4be1981222882c737e0e06214bce104c076ce431a1f7ff5c5361`.
- r2 helper source: `35fee3a73fc1b283c5412d577ccee8635caa26f6fbf251e10009566c3a18fbc6`.
- Read-only D2 runner source inspected: `43e93f7469c8dc3b0719f8f218ccb7f58f6860fcd5e0625e0fa580320d7e0c10`.
- Manifest: `frozen-manifest.json`.
- Evidence is synthetic CPU helper/test evidence only. No real checkpoint, runtime, MPS, rollout, training, integration, or campaign qualification was tested.
