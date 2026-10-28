# Uniform2 600-update continuation (r2)

Isolated, exactly-once campaign: restore the selected terminal60 `replica-2-uniform` learner (model, Adam, complete RNG
incl. MPS) and train 600 updates (9,830,400 decisions, constant LR 3e-5, same transformer/reward/PPO/normal starts/frozen
uniform pool of 512). The starting model and each saved 60-update boundary (11 policies) are evaluated on fresh cohort D6
`0xD6000000..0xD60003FF` (1024 complete normal-start games, sampled categorical, evaluation RNG 2026102803). Selection: largest
Q1 (bottom-256 mean), then Mean, exact tie keeps the earlier checkpoint. No official parent324 promotion; D5/B/E stay closed.

**Preparation only.** No launch, no source/gate acceptance, no ledger write, no checkpoint or GPU load. All frozen
predecessors are read and hash-pinned only.

## Design
- **Ten fresh-environment segments of 60 updates** (the accepted producer unit). A single env would need ~154k-entry per-slot
  seed lists, and native `batch_info()` returns them whole on every call (PPO deep-copies it per reset). Each segment starts at the
  saved `next_episode_indices`; the 64 in-flight episodes are abandoned explicitly and journaled/checkpointed at every boundary.
  Frozen `SeededTrainingAdapter`/`PreparedUpdates` run unmodified (their 60-update cap is the segment).
- `seeds.py`: owned extension of the frozen stream (same hash recipe, no 16384 bound; `start+15361` entries per slot). Cross-checked
  against the frozen helper whenever it fits; first-segment digests are registered, later ones journaled and re-derived by the audit.
- Learner restore reuses the parent-qualified path (`ckpt.restore_learner`, fingerprints must equal the receipt). RNG continues from the
  checkpoint; nothing reseeds the learner.
- Evaluation uses the accepted `_production_rows` (byte-identical in the producer package and the clean evaluator) on a **separate model
  instance loaded from the immutable saved checkpoint**. Learner RNG (python/numpy/torch CPU+MPS), grad mode, all module train/eval flags,
  model and Adam fingerprints are captured before and verified equal after every evaluation (also on fault).
- Roles are accounted separately (raw frames, constructors, steps, resets, seconds). Training budget 167,125,120 raw / 10 constructors /
  153,600 steps / 9,830,400 resets; evaluation 202,898,432 raw / 11,264 constructors / 202,752,000 steps / 0 resets (structural ceilings).
- Work cap 28,800 s (user maximum) + cleanup 10 + postflight 120 = 28,930 s; RSS = MPS = 6 GiB; retries 0. Projection: ~10.4 ks training
  (measured 1037.2 s/60 updates) + ~2.2 ks evaluation expected; 27.9 ks worst case if every evaluation episode hits the cap.
- Watchdog: `observe.py`, `execute_once.py` are byte-identical copies (direct-child ownership, non-reaping Darwin `waitid`). `power_guard.py`
  is an owned successor: native-root `caffeinate -ims` helper ownership always; AC needs both assertions; **battery is allowed only with the
  pinned `battery-power-override.json`** and then only `PreventUserIdleSystemSleep` is required. Historical guard untouched.
- Lease: exact lease in the main ledger (`active_long_campaign`, null beforehand), installed by `launch.py`, cleared only by `audit.py` after
  the durable audit and required parent stream receipt. The parent checker is source-hash-pinned and proves complete per-slot
  episode/reset assignment coverage, all ten stream digests, and exclusions before audit publication. Fresh attempt/launch markers, no retry, checkpoints chmod 0444 and never overwritten.

## Files
`binding.py` contracts/pins · `worker.py` campaign + `RealRuntime` · `terminal.py`/`audit.py` conservation + independent selection
recomputation · `launch.py` · `build_registration.py` · `finalize_registration.py` · `seal.py` · `monitor.py` (counts only) ·
`registration-schema.json` · `registration-draft.json` · `blockers.json` · `tests.py`; parent-owned `audit_segment_streams.py` independently checks terminal stream and assignment conservation.

## Activation (root; each step needs the parent)
1. `python -B seal.py` (only if source changed), independent review of `source-manifest.json`, source acceptance document.
2. Draft: `PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<pkg>/empty-pycache <venv python> -B build_registration.py --output registration-draft.json`.
3. Parent calibration acceptance → `finalize_registration.py`; gate acceptance (`binding.approval_document`, all `binding.GATES`).
4. `/usr/bin/caffeinate -ims /usr/bin/env PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<pkg>/empty-pycache <venv python> -B launch.py --registration ... --gate ... --source-acceptance ...` (each with `--...-sha256`).
5. Run the pinned parent `audit_segment_streams.py` after observer success and before `audit.py`; `audit.py` rejects a missing or mismatched receipt.
6. `audit.py --envelope <pkg>/launch-envelope.json --envelope-sha256 <SHA>`. A failed run needs parent incident handling; never retry.

## Tests
`PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<pkg>/tests-pycache <venv python> -B tests.py` — CPU stdlib fakes: seed extension vs frozen
helper, Q1 selection, power-guard AC/battery rules, full fake 600-update campaign (order, RNG preservation, fault handling, no retry,
lease install/clear) validated end to end by `terminal.validate_outputs`, tamper detection, budgets, pins. Not covered: native env with long
seed lists, real torch/MPS, checkpoint deserialization, `authenticate_module/class` on the loaded runtime, the real observer.
