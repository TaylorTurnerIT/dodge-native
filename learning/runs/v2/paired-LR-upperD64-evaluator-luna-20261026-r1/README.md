# Paired upper-D64 endpoint evaluator

Preparation only. No real game environment, model, checkpoint, training, or scheduled job ran. Tests used only synthetic fake policy/environment interfaces. Seed label: **unselected training-excluded upper-D development block; prior nonuse not proven**. Do not call this sealed or proven independent.

`paired_eval.py` imports only Python standard-library modules and performs no work on import. The explicit parent-only API is `evaluate_registered(...)`. It requires a registration file and exact byte SHA-256, a parent guard callback, checkpoint metadata SHA, a collector callback, and an output path. The linear endpoint SHA must arrive in that registration. The constant endpoint contract is fixed in source. This module never reads checkpoint binaries.

Collector contract: accept `seeds`, `difficulty=2`, `action_repeat=4`, `raw_frame_cap=18000`, `batch_size=1`, `gradients=False`, `action_mode="deterministic_argmax"`, and `reset_policy="construct_once_no_reset"`; return all 64 ordered raw rows. Parent integration must bind the collector to the reviewed frozen runtime, matching D2 startup/action/reward/death behavior, argmax over alive rows, preserved model mode, and no RNG/weight mutation. This helper does not import runtime code or construct `VecDodgeEnv`.

Raw rows receive strict seed/order, metadata, frame, boundary, death telemetry, and fixed-point score checks. Summaries report mean alive frames, bottom-16 Q1, top-16 Q4, death causes, truncations, and per-seed linear-minus-constant differences. Diagnostic only: one paired training seed (`4200000001`), no replicate uncertainty, and LR average differs (`2e-5` linear, `3e-5` constant), so no causal schedule-order claim. Existing operational dev64 retention/gates remain parent-controlled.

Before any future call, parent must review/freeze this source, provide a complete registration and linear checkpoint metadata pin/receipt, verify budgets/runtime/model pins, supply an active guard, and decide execution. No auto-execution, fallback seed, registration, timing claim, or retention change exists here.

CPU synthetic tests only:

```sh
cd /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/paired-LR-upperD64-evaluator-luna-20261026-r1
PYTHONPATH= PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -m unittest -v
```
