# Frozen source-only review: expanded evaluation runner r2

Verdict: **BLOCKED. No launch clearance.** Four blockers and several high/medium issues. Parent owns lease, marker, and launch decisions; nothing here clears a launch.

## Scope and method

- Read-only. No runner code executed or imported; no native, MPS, checkpoint, game, training, lease, marker, or child process touched. No shared edits.
- Read: `build_registration.py`, `execute_once.py`, `worker.py`, `test_runner.py`, `manifest.json`, `README.md`, and parent `findings.json`.
- For ledger key names and proposal policy I parsed a few JSON artifacts with a read-only one-line Python `json.load` (no runner code, no imports of the sources). Disclosed here because the scope said no execution.
- Parent's reported reproductions (NameError in ranking/confirmation draft; benchmark stage bundle rejected by receipt builder; fabricated test receipts) are confirmed **by source reading only**. I did not run them.

## Source hashes (sha256, re-checked at review end; unchanged from manifest)

| file | sha256 |
|---|---|
| build_registration.py | 3133af2663c065687dd8f610245e889e492e3c1b140f8235bee9263e9297ee87 |
| execute_once.py | 1426486b16928f4cb716b3a8891fbc77c79a24d7e2b12d12cf3fb24c7bea4bcc |
| test_runner.py | 36303687a39237c612855a23dd284a5d56455de46dd83721b60889d553349fdc |
| worker.py | 8af27fe3bf768cfff7716fe5b823ad1910d479f5d4810a73521f0e5099606e18 |
| manifest.json | 58ddc93667fbfb25fa3b19ec3df62c7650f5b6ed72da4863f60b2f41bdd6e17b |
| README.md | 46ba255488677228c1a8ffb140dd12e1d62ba9fed7c4f5be66efdbd74a09fd69 |
| evaluator (expanded-evaluator-publication-repair-parent-20261026-r4/expanded_eval.py) | a3439c33152b082471cd9f9a36ef4bb03783b9544ae7c1e3fe1878e607b128aa |

Evaluator is pinned only; its contents were not reviewed here (separate review).

## Blockers

**B1. Ranking/confirmation draft always raises NameError.** `build_registration.py:69-70` uses `limits[...]` but `make_draft` never defines `limits`; the registration dict on line 71 inlines it. Trigger: `make_draft(mode='ranking'|'confirmation')` with a valid receipt. Consequence: no ranking or confirmation draft. Note: parent cited lines 80-81; the file is 109 lines and the fault is at 69-70. Tests miss it: `test_runner.py:159-166` only exercises benchmark mode.
Fix: build the `limits` dict before `reg`, then add ranking/confirmation tests.

**B2. Successful benchmark output can never pass the throughput receipt check.** Benchmark stage writes `expanded_D2_stage_bundle_v1` with a `results` list (`worker.py:196-197`, `exclusive_json(out, results)`). Both readers demand `expanded_eval_dev64_benchmark_receipt_v1` with `repeats`, per-repeat `raw_frames`, `elapsed_seconds`, `complete`, `candidate_update==348`, `cohort_name`: `build_registration.py:21-37` (checks at 24-25) and `execute_once.py:79-104` (checks at 83-84). Nothing in the runner writes that receipt. Trigger: any real benchmark run followed by ranking/confirmation preflight. Consequence: ranking and confirmation are blocked after a valid benchmark, and the only way forward is a hand-written receipt that is merely sha-pinned, not produced by the run.
The test suite agrees with the worker, not the readers: `test_runner.py:81` asserts `['results']` on the bundle, while `ranking_setup` (`test_runner.py:63-72`) and `confirmation_setup` (`test_runner.py:43-60`) fabricate the receipt. Neither a real chain nor a bundle-to-receipt conversion is tested.
Fix: one producer of the dev64 receipt, written by the runner from the two repeat outputs with raw-frame and elapsed fields defined, and consumed unchanged by builder and preflight. Needs a design decision on where `raw_frames` and `elapsed_seconds` come from.

**B3. Lease guard reads the wrong ledger keys, so the active-long check is vacuous.** Runner reads `active_long` and `active_inference`: `worker.py:65-67`, `execute_once.py:121-122`, `execute_once.py:223`, `execute_once.py:256`. The ledger uses `active_long_campaign` and `active_inference_diagnostic` (observed in `user-best-checkpoint-policy-20261026-r1/state-after.json`; `active_inference` not seen there). `.get('active_long')` is always `None`, so a running long campaign passes every guard. Trigger: long training campaign active while an evaluation starts or runs. Consequence: concurrent GPU/RSS contention and a silent breach of single-lease serialization. The fixture invents the same wrong keys (`test_runner.py:25`, `:107`), so the 16 tests cannot catch this.
Fix: check `active_long_campaign` (exact name) is `None`/`False`; keep the exact `active_inference_diagnostic == expected_lease` check; resolve `active_inference` (see policy note).

**B4. SIGTERM/SIGHUP to the supervisor bypasses cleanup.** Cleanup and receipt live in `except BaseException` (`execute_once.py:230-237`), but the child runs in its own session (`start_new_session=True`, line 201). A default SIGTERM/SIGHUP kills the Python supervisor without raising, so no `terminate_bounded`, no outer receipt, and the claimed marker stays. Trigger: session teardown or `kill <launcher>`. Consequence: unattended worker keeps running with RSS/MPS unbounded; marker blocks any retry. SIGKILL cannot be handled; mention in limits.
Fix: install SIGTERM/SIGHUP handlers that raise into the existing except path.

## High

**H1. Test suite disables the production checks it claims to cover.** `test_runner.py:16` sets `VERIFY_FROZEN_RUNTIME` and `VERIFY_PROPOSAL_CANDIDATES` to `False` in the launcher copy; `test_runner.py:15-17` rewrites the native SHA, golden path and SHA, and CAP. So frozen runtime pins, proposal-candidate pins, and the real constants never run under test. "16 pass" is weaker than the README implies.

**H2. `active_procs` failures escape cleanup and skip the receipt.** `ps` runs with `timeout=0.2` and any failure raises (`execute_once.py:36-42`). Called at 207, 228, 233, 240, 244, 282, 291. Line 240 is outside the `try`, so an exception there propagates with no outer receipt. Lines 232-233 inside the except handler can raise before the receipt write at 236. Trigger: `ps` slow (>0.2 s under load) at stop or post-exit. Consequence: no partial receipt, possibly unreaped child.

**H3. Heartbeat freshness depends on the evaluator calling `check_guard` often enough.** Heartbeat is written only in `worker_guard` (`worker.py:56-79`), and stale threshold is 2.0 s in the draft (`build_registration.py:71`), up to 5 s allowed (`execute_once.py:132`). Any evaluator span >2 s without a guard call (checkpoint load, long native batch, MPS compile) gets killed as `heartbeat_invalid` while healthy. Needs the evaluator's guard-call cadence verified before launch.

**H4. MPS cap fails open.** `driver_memory` returns `0` when torch is not loaded (`worker.py:90`) and when MPS is unavailable (`worker.py:93`). In an `mps` run, if torch is loaded but `torch.backends.mps.is_available()` is false, the cap silently passes. Fix: when registration backend is `mps`, a missing or unavailable reading must fail closed.

## Medium

**M1. Exact-dict lease comparison is brittle.** `execute_once.py:120,223,253` and `worker.py:65` compare the whole `active_inference_diagnostic` object to `expected_lease`. The live lease object carries mutable fields (observed: `cancel_requested`, `campaign_launch_authorized`, `harness_sha256`). Any field update false-stops the run (`lease_invalid`). Fix: compare an immutable identity field.

**M2. Winner selection is not re-derived or checked against the proposal comparator.** Ranking winner is max `performance.mean`, tie to lower update (`worker.py:193-196`). Proposal specifies `ranking_metric: mean_alive_frames_all_1024_including_caps`, `tie_break: earlier_phase_update`. Match holds only if the evaluator's `performance.mean` equals that metric; nothing checks cohort size 1024 or episode count. `validate_selection` (`worker.py:110-130`) also trusts the parent's `winner_update` and never recomputes argmax from the six referenced results.

**M3. Ranking results not bound to this run.** `validate_selection` checks `complete`, `cohort_name`, update, and checkpoint SHA only (`worker.py:123-130`). No registration SHA, run_id, evaluator SHA, or cohort SHA on the referenced result files, so results from another run could be pinned.

**M4. Outer receipt path not in output ownership checks.** `check_mode` plans only evaluator outputs (`execute_once.py:66-72`). `stage.json.outer-receipt.json` is written with `os.link` (`atomic_json`, line 31); if it already exists, the `FileExistsError` at line 236 masks the stop reason and skips `raise`. Add to preflight.

**M5. Cleanup budget edge case.** `terminate_bounded` computes `end=min(now+10, deadline+10)` (`execute_once.py:276`). If the stop is detected after `deadline+10`, `term_end` lands in the past: SIGKILL goes out with zero SIGTERM grace (`:279-288`). Also `proc.returncode` may still be `None` at `:238` in that path.

**M6. Builder `validate_final` relies on preflight for several pins.** It does not verify cohort manifest SHAs, candidate pins against proposal, or runtime root/versions against the training registration. Preflight does (`execute_once.py:144-158`), so this is defense-in-depth gap, not an open hole, provided preflight always runs.

## Low / notes

- `successful_receipt` and `validate_throughput_receipt` assume `raw_frames == sum(alive_frames)` (`build_registration.py:32`, `execute_once.py:91`). Proposal says `raw_frame_conservation: required_per_episode`; confirm the evaluator's definition.
- Projection `ceil(2*elapsed/raw*cap+10)` uses two 64-episode calls to project six 1024-episode calls; per-call fixed cost (import, checkpoint load) is amortized differently. Probably conservative, not verified. Work budget is a hard stop with no resume, so underprojection yields partial output.
- `worker.log` is unbounded (`execute_once.py:200`); disk exhaustion from a chatty evaluator is not capped.
- Child processes that leave the process group (setsid) are not detected by `ps` group sampling.
- Launcher imports `worker` in-process for `validate_selection` (`execute_once.py:161,266`). Top-level of `worker.py` is import-safe; fine as is.
- `saved!=result` (`worker.py:181`) fails closed on any JSON round-trip difference (tuples, NaN); expected, not a bug.

## Policy clarification requested by parent (lease and concurrency)

Proposal `concurrency` block: `current_legacy_lease: completed348_parent_finalization_cleared_exactmatching_lease; newregistry_not_installed`; `evaluation_jobs: registered and serialized against training or represented as capacity jobs`; concurrent launch requires a "separately reviewed concurrent registry successor; no frozen guard changes"; "standalone serialized evaluation does not require it." `initial_max_active_training_campaigns: 2` is a separate training-side allowance. Per-run fields (`owner_token`, `seed_vector_sha256`, `resource_sampler`, `observer_receipts`, etc.) belong to the concurrent successor only.

Reading: current runner policy should be **serialized single-lease**. Required at launch: `active_long_campaign` is `None`/`False`, `active_inference_diagnostic == expected_lease` exact identity, and no other inference lease. `active_inference` should be dropped or defined in the ledger, not invented. Do not add concurrency relaxation to this runner. If parent wants evaluation concurrent with training, that is the separate successor, not a flag here.

## Parent-requested assessments, mapped

- Launch reachability and mutation order: preflight (no marker) → marker claim (`execute_once.py:192`) → output mkdir → worker. Preflight does not create marker, output, or log. Ordering is correct; TOCTOU window between preflight and claim is small but not rechecked after claim (window only).
- Cleanup, signals, resource accounting: see B4, H2, M5, H4. RSS sampling is process-group based (`ps`), not psutil, on the supervisor side; worker-side uses psutil or `ps`.
- Final schema and metadata: `validate_final` set checks are good; `run_id` placeholder, `state_path`, `expected_lease` non-null checks present. `validate_final` does not check `evaluator_candidate_sha256` against evaluator review; relies on the pending status gate (`build_registration.py:78`).
- Registration and source pins: pins verified at preflight and postflight; draft leaves worker/launcher SHA `None` by design. OK.
- Output ownership and exact golden: golden 348 compared in worker (`worker.py:184-187`) and receipt reader (`execute_once.py:94`) over 12 fields. Good. Output collision checked pre-claim (`execute_once.py:70,72`) and in worker (`worker.py:106-107`). Good except M4.
- Other cohorts: unopened, as requested.

## Limits

- Source-only; nothing executed. Parent's reproductions confirmed by reading, not by running.
- Evaluator source not reviewed here (pinned only). H3 and B2 depend on evaluator behavior (guard cadence, `raw_frames`/`elapsed_seconds` output).
- Native, MPS, checkpoint, game behavior unverified.
- The 16-test count and fake-process results are taken from README; not re-run.
- Proposal and ledger facts from read-only JSON parsing; ledger observed in one state file (`user-best-checkpoint-policy-20261026-r1/state-after.json`); the live ledger was not checked for other key names.
