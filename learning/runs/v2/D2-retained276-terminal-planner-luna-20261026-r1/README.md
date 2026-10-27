# Retained276 terminal planner

Pure CPU calculator for a parent decision after the registered 276→348 run and full strict audit finish. It cannot accept a run, edit state, clear a lease, select a checkpoint, or authorize follow-on training. Its output is a proposal with every authority flag false.

## Future invocation

Parent must first supply one externally pinned JSON document using `retained276_terminal_planner_evidence_v1`. Normalize the completed strict wrapper record into `audit`, preserving its full-mode schema, auditor/wrapper/observer/registration hashes, all seven audited updates, candidate checkpoint/certificate/sidecar hashes, pin counts, and current-parent binding. Bind `registration` to seed `3791628419`, config SHA `f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628`, run ID `D2-retained276-continuation-20261026-r2`, and exact parent. Supply `performance` from all seven audited certificates: update, checkpoint and certificate hashes, mean alive frames, Q1 bottom16 mean, Q4 top16 mean, episodes, deaths, caps, and nonzero death causes. Keep mean score informational; planner never selects on it.

Supply exact `candidate_metadata` for updates 276, 288, 300, 312, 324, 336, and 348. Each record must bind phase update, checkpoint hash, sidecar SHA-256, source metadata SHA-256, learner counters, cumulative counters, next episode indices, model/optimizer/RNG fingerprints, and `cumulative_selected_checkpoint_trajectory_wall_seconds`. Preserve these source records unchanged. `parent.receipt` must be the exact accepted 276 receipt with SHA `d64d0f803d02a8d2c33da9fa0ba862f06ba7d9c56dcf4f0494e559a49e48fcc4`.

`terminal` must include successful execution and worker status, raw exits, SHA-256 values for execution result, worker result, observer record, and resource log, resource peaks, process absence, source postflight, final-publication absence, full observed outer seconds, and terminal cumulative counters and next episode indices. Bind evidence to observer source SHA `e3782f1c28c05548e995f3cb8c1a41b2a66f77b69d9455cada0be465f950ad95`. `parent` carries exact retained276 checkpoint and receipt, baseline mean, and `stale: false`. `pins` must match source pins compiled into planner.

Run only after terminal/audit evidence exists:

```sh
python3 -B learning/runs/v2/D2-retained276-terminal-planner-luna-20261026-r1/planner.py \
  --evidence /absolute/path/to/parent-prepared-planner-evidence.json \
  --output learning/runs/v2/D2-retained276-terminal-planner-luna-20261026-r1/proposed-plan.json
```

CLI reads supplied evidence and writes only `proposed-plan.json` inside this owned directory. Blocked evidence writes a `blocked_fail_closed` plan and exits 2. Parent must independently decide actual acceptance and bind exact source evidence. The proposal is not an accepted receipt.

## Clock rules

- Keep saved candidate trajectory, selected future-branch high-water, and full completed-campaign resource cost separate.
- No improvement or a baseline tie retains the exact 276 checkpoint and its receipt metadata. Future branch stays `4760.062404125177`; full campaign cost adds observed outer seconds to `5537.773026792208`.
- A better intermediate retains its exact checkpoint metadata and candidate-point trajectory. Bind completed terminal counters separately. Do not pretend the model trained through discarded tail updates. Full campaign cost still includes all observed outer seconds.
- A better endpoint adds all observed outer seconds to future branch high-water. Full campaign cost also adds all observed outer seconds.
- Strict improvement uses mean alive frames. Chronological ties keep the earlier retained candidate. Q1/Q4 are bottom/top 16 alive frames; mean score is excluded.

## Tests

```sh
python3 -B learning/runs/v2/D2-retained276-terminal-planner-luna-20261026-r1/test_planner.py -v
```

Tests use synthetic in-memory records only. They do not open checkpoints or run outputs.
