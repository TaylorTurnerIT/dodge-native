# D2 retained-276 continuation: frozen source review

Reviewer: independent Haiku review, source-only. Target: `learning/runs/v2/D2-retained276-continuation-prepare-luna-20261026-r1/` (registration `30a29080…1b17a7`, source manifest `08fa5315…e640`).

## Verdict

**No launch blockers.** Two low-severity advisories, neither required to launch. Parent may proceed to lease install and fresh unmocked preflight under the parent-owned gates.

## What was checked

- Source hashes: all 11 files in `source-manifest.json` match on disk. `registration.json` pins 13786 items, including the current `runner.py`, `execute_once.py`, config, parent checkpoint, parent terminal receipt, sidecar, audit, full audit, selection, metadata, and registration.
- Parent authority: `parent-terminal-receipt.json` (d64d0f80) is schema `d2_normal_training_parent_terminal_receipt_v1`, `accepted_completed_normal_training_iteration`. Counters 72 / 9216 / 1179648 / 4713702, inherited 252, cumulative 324. Cumulative sums reconcile.
- Parent metadata: `selected-checkpoint-metadata.json` matches the receipt on counters, episode indices, identity, fingerprints, policy, runtime, native, config, and wall fields. The hardcoded `5518.087640292119` equals `4129.757 + 1388.331`, so it is the parent's own point clock.
- Wall clocks: future trajectory baseline `4760.062404125177` and campaign cost `5537.773026792208` are used as baselines. The parent point clock `4740.377` is kept separate. Future-checkpoint fields are baseline plus current outer elapsed.
- Budget: `1408.0161675 × 9216/9216 × 1.15 = 1619.2186`. Preregistered work `1650` is under the hard work cap `1790` and the outer cap `1800`.
- LR: config `0.0001`, Adam built at `0.0001`, saved and effective LR asserted before and after PPO and at each checkpoint. Predecessor LR-override path removed; config bytes equal parent.
- Restore order: parent load → validate → model → Adam → `restore_learner` (restores RNG via `restore_rng(…, "mps")`) → fingerprint compare → only then env construction.
- Entry gate: 276 evaluation runs before any gradient and compares 64 rows against `development-000276.json`, which exists.
- Resume indices: from parent `next_episode_indices`, fresh env seed `3791628419`, 64 abandoned episodes recorded.
- Launcher: `-B`, `PYTHONDONTWRITEBYTECODE=1`, empty pycache prefix (verified empty), runner checks bytecode policy and interpreter resolution.
- Outputs: no `.pyc` found under the prep dir or parent run dir.
- Attempt-log hashes in the receipt match the files.

## Advisories (non-blocking)

**A1 (low, evidence accounting).** `preparation-receipt.json` `retained_failed_attempts` labels do not match their logs.
- `attempts/preflight-attempt-01.log` fails with "Full audit candidate set differs". The receipt calls it a runtime-continuity pin defect.
- `attempts/preflight-attempt-02.log` passes ("registration valid; pins=13786"). The receipt calls it a full-audit label mismatch.
- The runtime-continuity traceback is in top-level `preflight.log` (22:38), which is superseded and not listed.
- Receipt cites 5 failures; `attempts/` holds 18 logs. Recommend a new accounting note. Do not edit the receipt.

**A2 (low, integrity check strength).** `runner.py:297` `validate_runtime_continuity` compares `source_runtime_root` with `reg["runtime_root"]`. Both are `…/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime`, so the per-member byte comparison compares a tree with itself. Real binding still holds through `verify_pins` plus the pinned-member digest equal to `runtime_sha256 = PARENT_RUNTIME_SHA (2cf10e9f…)`. Optional fix only.

## Residual risks

- MPS RNG restore is not exercised by the CPU test. The worker fails closed if the restored RNG fingerprint differs from the parent (`ed93fb48…`). Parent's fresh preflight and actual one-shot must confirm.
- Full unmocked preflight with the real lease is parent-owned. Only the exact lease assertion was mocked in preparation.
- `docs/implementation-plan-v2.md` and `docs/SPEC_PRIVILEGED_VIT_RL.md` got a grep only (no continuation/retained-276 terms found). Full text not reviewed within the time cap.
- Calibration defects not checked (out of scope per instructions).
