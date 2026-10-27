# Fixed terminal full-run evaluation

Source-review preparation only. No campaign, model load, or native environment was used while preparing this package.

The watchdog (`observe.py`) and cleanup (`execute_once.py`) are byte-identical copies of the accepted opening-maintenance supervisor. Evaluation-specific `binding.py`, `terminal.py`, and `worker.py` reuse the clean reviewed `expanded_eval.py` collector. The one worker evaluates the six predetermined terminal-60 endpoints and parent 324 sequentially on the same 1,024 seeds. Every policy has a separate spent claim. Failure stops the campaign without retries or seed replacement.

Each endpoint retains its actual producer registration and full expected learner identity. Control 1 uses its accepted legacy producer identity, while inference always uses the clean current runtime. Registered runtime members differ only in the unused training scheduler. The legacy cache incident is preserved; no legacy module is imported.

Raw gameplay and startup costs are journaled per returned native call. Lease/RSS/MPS sampling runs every 0.2 seconds; cheap wall, raw-frame, and cancellation checks run at every collector guard. Normal starts, sampled categorical actions, four frames per decision, 18,000-frame cap, and disabled practice cutoffs remain fixed.

The comparison reports Worst, Q1 (bottom-quarter mean), Mean, Q4 (top-quarter mean), Best, milestones, death causes, and per-replica paired differences. The fixed 2,000-draw paired percentile bootstrap measures evaluation-seed uncertainty conditional on the trained policies and sampled-action realization. Three training-seed pairs remain descriptive. Parent 324 is evaluated once. No selection or promotion is performed.

## Parent binding and execution

1. Inspect `registration-draft.json`, all producer pins, and the proposed sampling RNG seed. The historical timing projection is **not** fresh same-runtime MPS calibration. Bind accepted calibration evidence, wall budget, and numeric RNG before any evaluation.
2. Obtain independent source review of the exact `source-manifest.json`. Copy the draft to a new `registration-final.json`, set `status` to `parent_registered`, and bind `calibration.parent_accepted` only when its evidence is accepted. Do not edit a frozen reviewed registration.
3. Write parent source acceptance with `status: accepted_source_review_only` and exact `source_manifest_sha256`. Write gate acceptance with schema `progressive1000_full_evaluation_gate_acceptance_v2`, status `approved_exactly_once_fixed_full_run_evaluation`, exact `registration_sha256`, every `binding.GATES` value `passed`, and byte-pinned external review/calibration records in `pins`.
4. Use the lexical venv interpreter with `-B`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONPYCACHEPREFIX` set to the registered empty cache. Run `launch.py --registration ... --registration-sha256 ... --gate ... --gate-sha256 ... --source-acceptance ... --source-acceptance-sha256 ...`. The launcher installs its exact lease and marker, then directly waits for the existing watchdog. It does not clear the lease.
5. On terminal exit, inspect raw observer evidence before results. Run `audit.py --envelope <package>/launch-envelope.json --envelope-sha256 <SHA>`, with the same interpreter/cache environment. The audit proves process-group absence, input/cache identity, complete native cost conservation, all 7,168 rows, comparison reconstruction, and independent bootstrap reconstruction. Only a durable successful parent audit clears this exact lease. A failed or partial run needs explicit parent incident handling; do not retry or clear markers.

`build_registration.py` is hash-only and refuses output outside this package. It never installs a lease, writes a marker, imports Torch/native modules, or deserializes checkpoints. `tests.py` uses stdlib and synthetic rows only. The draft and source review are not launch authority.
