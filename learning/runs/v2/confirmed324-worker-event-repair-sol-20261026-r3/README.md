# Confirmed324 worker event repair R3

Source-only successor to `confirmed324-paired-worker-contract-repair-sol-20261026-r2/`, repairing the sole R2 source blocker, R2-01/P2. Parent acceptance and all runtime/launch authority remain pending. No real Torch, NumPy, native or MPS import, accepted checkpoint deserialization, training, evaluation, selection, campaign launch, subdelegation, commit or push occurred.

## Event ownership and failure contract

`RuntimeAdapter.update(guard, progress, journal_collection_events)` calls the worker's synchronous callback exactly once immediately after successful collection, before observation reassignment, PPO or diagnostic validation. The callback receives deep copies of completed/reset event lists; mutations cannot change the collection. Its return value is ignored. This callback is distinct from the unchanged accepted R5 restore/capture callbacks.

The worker orders events with the unchanged pinned historical `ordered_episode_events`, retaining complete payloads and `phase_update=324+local`. It writes, flushes and fsyncs each event before returning to the adapter. The worker does not journal those events again after update success. Empty event collections still invoke the callback once.

Any event serialization, write, flush, fsync or callback exception propagates before PPO. The worker records failure, retains the written prefix and available progress, closes the environment, and saves no candidate for the failed update. The durable R5 claim remains spent; no write, callback, collection or claim is retried. A failed fsync does not establish crash durability for that record; prior successfully synced records remain the durable prefix. A partial write is retained without repair. PPO or post-PPO validation failures retain the previously synced collection events. Update counters advance only after PPO and all diagnostics succeed; diagnostic progress may report a complete PPO while accepted worker update counters remain unchanged.

R5 `transition.py`, `driver_binding.py`, `attempt_claim.py`, `fingerprints.py` and `rng_reference.py` remain byte-identical. Private globals, source-byte/function/default/dependency bindings, durable claim-before-accepted-restore, zero-argument restore-once and actual return evidence, failure consumption, full fingerprints, reseeding, LR override after Adam restore, episode indices, counters and candidate controls remain unchanged. Disposable constructor seed/model/Adam bootstrap before the R5 claim remains the explicitly accepted source boundary. No accepted state is restored before that claim.

## Evidence and inert registrations

- `tests.log` and `fake-test-summary.json`: all original 37 controls, with only the two fake update signatures/callback interface adjusted, plus six focused event controls. The new controls exercise actual worker execution, actual adapter update, actual R5 transition and private restore bodies against synthetic state/APIs. Owned temporary files are removed. Fake outputs never deserialize accepted checkpoints or qualify real runtime behavior.
- `interpreter.json`, `receipt.json`: actual project `python/.venv/bin/python -B`, bytecode/cache policy, results, limits and remaining gates.
- `input-manifest.json`: unchanged original 58 immutable input pins. `preflight.json` and `postflight.json` also pin/check all R2 and review files. The parent ledger `learning/runs/v2-orchestration/state.json` is observed separately, outside the immutable set; concurrent parent changes are permitted and never edited here.
- `exact-diff.patch`, `diff-index.json`: reproducible exact text diff from R2 for every successor source/config/documentation member, including explicit unchanged R5 entries. Evidence logs and self-referential manifests are excluded from the patch and inventoried separately.
- `source-manifest.json`: authoritative successor source inventory, not acceptance. `artifact-manifest.json` inventories every delivered file except itself, including receipt and source manifest. Both manifests carry no parent authorization.
- Six regenerated `registration-template-replica-{1,2,3}-{A,B}.json` remain `parent_review_required_not_launchable`, with parent placeholders. They bind the unchanged input-manifest SHA; the parent must insert this successor's final source-manifest SHA in six final registrations. No registration, lease or marker was created or modified.

`build_evidence.py prepare` was used before testing to regenerate templates, exact diff and source manifest; `freeze` verifies inputs/source and writes terminal evidence. `verify` is read-only. Files are frozen read-only at handoff; use another successor for repairs or replay. No predecessor tests or scripts were executed in their own directories.

## Study and parent gates

Scope remains three exploratory paired LR comparisons from accepted phase324/cumulative372: constant `3e-5` versus linear `3e-5` to `1e-5` over 60 updates, cumulative373–432/phase325–384. No formal methods claim at n=3, curriculum changes, checkpoint selection or promotion. Candidate positions remain local12/24/36/48/60. Accepted initial CPU/MPS references prove initial generator states only.

Parent still owns independent source acceptance; supervision, watchdog, cancellation and cleanup integration; resource calibration/caps; six final registrations, leases and launch gates; real loaded runtime/class/backend and accepted model/Adam/RNG restoration qualification; native seed readbacks, rollout/PPO/diagnostics, true candidate serialization and terminal audit; separate full normal-start evaluation and selection. Templates remain inert and this repair grants no launch eligibility. No broad watchdog or package-pin features were added.
