# D2-retained348 finalizer r3 review (Haiku 5.5, `claude-haiku-5-5`)

Scope: source-only review of `learning/runs/v2/D2-retained348-linear-finalizer-prepare-parent-20261026-r3/` (`finalize_parent.py` SHA-256 `1daeafc01e4063e2f93ddeb5b73b815e201d49a9b54c4d44c83e0677f4d79495`, matches `preparation-manifest.json` `source_sha256`; test and README hashes also match the manifest).

Method: read `finalize_parent.py`, both tests, README, preparation-manifest, `cpu-tests.log`. Read-only `grep`, `jq`, `shasum` over frozen JSON evidence, prep/runtime source, and the ledger `learning/runs/v2-orchestration/state.json`. No Python imported or run. No tests run. No checkpoint load, MPS, eval, training, lease or ledger write, no shared edits. Only this directory was written.

Prior review: `D2-retained348-finalizer-review-haiku-20261026-r1/report.md` (SHA-256 `568cea2d55db92cf5f3e1a8dccfb989187ad305a1740fef6d670bd8f41783647`) reviewed r1 `687130a4…`.

## Verdict: BLOCKER

Not clean. Two blockers. Do not copy and invoke r3 in its current form.

## Blockers

### B1. `ast.literal_eval` rejects the pinned schedule spec, after three outputs are already written

- Trigger: every invocation that passes the pre-write gates. First call is `finalize_parent.py:502` (`schedule_spec = read_json_from_bytes(worker_schedule_bytes)`). Same helper called at `:504` and `:540`.
- Cause: helper at `:718-727` runs `ast.literal_eval(node.value)` on `SCHEDULE_SPEC`. Both pinned copies of `lr_schedule.py` define it with Name references, not literals:
  - prep `D2-retained324-linear-integrated-luna-20261026-r4/lr_schedule.py` lines 17-20: `"origin_cumulative_update": ORIGIN_CUMULATIVE_UPDATE`, `"horizon_updates": HORIZON_UPDATES, "start_lr": START_LR, "end_lr": END_LR`.
  - auditor `D2-retained324-linear-auditor-prepare-luna-20261026-r3/lr_schedule.py` lines 17-20, same names.
  - `literal_eval` does not resolve module-level names. Result: `ValueError: malformed node`.
- Consequence: `finalizer-assembly.json` (`:438`), `audit.json` (`:464`), `completed-iteration-receipt.json` (`:494`) are written. Not written: `retained-best-candidate-receipt.json`, decision, `report.md`, precommit and state snapshots, output manifest, ledger commit, lease clear. Ledger is untouched (safe), but the output directory holds a half-accepted state. `"x"`-mode writes make a rerun fail, so recovery needs a new reviewed preparation.
- Masked by tests: `test_publication.py:44-47` writes `repr()` of a pure-literal dict into the synthetic `lr_schedule.py`. `test_finalizer_contract.py:35` uses a literal source string. No control reads the real pinned schedule bytes.
- Fix direction (not applied): resolve module-level constant Names from the same AST, or hard-code the spec and cross-check canonical SHA plus AST equivalence against both pinned files. Add a control fed the real pinned bytes of both copies. Move every read and parse that can fail (`:496-540` inputs) to before the first write at `:438`, so any failure is pre-write.

### B2. Two frozen-evidence bindings the finalizer requires are absent, so it aborts before any write on production inputs

Fail-closed, so no partial output. But the finalizer cannot complete as written.

- (a) `finalize_parent.py:255-259` (exact check at `:257`). `audit["tracked_file_sha256"].get(str(manifest_path))` for `D2-retained324-linear-lr-20261026-r1/artifact-manifest.json`. The frozen `full-audit.json` tracked set has 29 keys; `execution-result.json` and `worker-result.json` for this run are present, `artifact-manifest.json` is not. `.get` returns `None`, `need` raises. Trigger: every invocation, first failure in `_verify_registered_evidence` (`:356`). Consequence: `ValueError` before any write.
  - Decision needed, not a silent drop. The 32 registered output hashes are still checked against real files (`:245-252`), but the manifest file's own hash is not audit-covered. Either accept and document that weaker binding, or re-audit.
- (b) `finalize_parent.py:265-267`. Clause `reg["pins"].get(str(observer_source)) == sha(observer_source)`, with `observer_source = D2-retained324-linear-execution-observer-parent-20261026-r1/observe.py`. That path is absent from the registration pins. The 10 `retained324-linear` pin entries are all r4 prep files. Registration SHA `0a6bf982…` is frozen, so the pin cannot be added. The first clause (`binding["observer_source"]["sha256"]`, binding pinned at `BINDING_SHA`) already covers the observer and is audit-covered. Fix direction: drop the registration-pins clause and rely on the audit-binding clause.

## Verified

- Original B1 (r1) fixed. `_load_selected_state` returns six values (`:336`). Caller unpacks six (`:404`). `schedule_fields` is bound and used at `:540`.
- N1 (r1) fixed. `os.fchmod` on the temp descriptor to the original mode (`:696`). Ledger `state.json` mode is `-rw-------`, so it is preserved. Owner, group, ACLs and xattrs are not preserved (minor, see N11).
- Name check. Every name in `_validate_and_finalize`, `_load_selected_state`, `_verify_registered_evidence`, `guard`, `validate_review_reconciliation`, `_check_live_process_absence` and the helpers is defined at module scope or imported (`Counter`, `base64`, `datetime`, `timezone`, `hashlib`, `json`, `math`, `os`, `Path`, `subprocess`, `sys`, `tempfile`). No other NameError found.
- Key names exist in the real artifacts:
  - Registration: `native.sha256`, `parent.latest_resource_cost_anchor.path`, `parent.registration_sha256`, `lr_schedule{origin_cumulative_update,horizon_updates,spec_sha256}`, `expected_outputs` (32), `import_policy.pycache_prefix`, `config_sha256`, `runtime_sha256`, `policy_sha256`, `lr_schedule_path`, `lr_schedule_sha256`, `state_path`, `expected_lease`.
  - Full audit: `audit.{status,candidates,terminal_record_sha256,tracked_file_sha256,pins_checked_before_and_after=13857,proposed_best_update=348,registration_sha256}`, `mode`, `reviewed_manifest.sha256`. Candidate entries have `mean_alive_frames`, `checkpoint_sha256`, `sidecar_sha256`, `certificate_sha256`, `component_fingerprints{model,Adam,RNG}`, `performance`.
  - Worker: `counters`, `cumulative_counters`, `elapsed_seconds`, `current_iteration_observed_outer_seconds`, `cumulative_selected_checkpoint_trajectory_wall_seconds`, `peak_rss_bytes`, `peak_mps_driver_bytes`, `updates`.
  - Execution and observation: `execution_result` nested keys, `worker_pid`, `owned_pgid`, `outer_process_group`, `observer_pid`, `outer_pid`, `launch_count`, flags.
  - Old receipt: `evaluation_path`, `evaluation_sha256`, `performance{mean_alive_frames,q1_bottom16_mean,q4_top16_mean,death_causes,...}`. Its `evaluation_sha256` (`73f9ee…`) matches the file on disk.
  - Certificate: `evaluation{rows,complete,deaths,caps,mean_alive_frames,mean_score}`. Sidecar: `checkpoint_sha256`, `eligibility_status`, `promoted`, `training_eligible`.
  - Cost anchor: `wall_accounting.completed_campaign_resource_cost_after_seconds`. Path is pinned in the registration and its SHA (`d3ddc4…`) matches.
- Checkpoint writer (`runner.py` ~886-910, ~1000-1005) emits every key the finalizer reads: `lr_schedule`, `counters`, `inherited_counters`, `cumulative_counters`, `identity`, `identity_sha256`, `run_seed`, `config_sha256`, `runtime_sha256`, `native_sha256`, `policy_sha256`, `phase_update`, `local_update`, `current_iteration_observed_outer_seconds`, `cumulative_selected_checkpoint_trajectory_wall_seconds`, `update_progress`, `next_episode_indices`.
- Schedule writer. `new_schedule_state` (`lr_schedule.py` 53-66) emits the four fields that `schedule_field_mapping` maps, plus `optimizer_param_group_count`.
- API. `load_checkpoint(path, expected_identity=None, expected_sha256=None)` matches the call at `:312`. `dodge_rl.identity.identity_hash` exists. `runner.fingerprint` and `runner.validate_saved_schedule_lr` exist.
- Import side effects. `runner.py` loads `lr_schedule` through a pinned path (`LR_SCHEDULE_SHA256 ef81e8…`), so there is no shadowing. Runtime root contains only `dodge_rl/`.
- Ledger. `active_long_campaign` equals `reg.expected_lease`. `active_inference_diagnostic`, `active_inference_campaign`, `active_inference_lease` and `cancel_requested` are null. `tasks` has 307 entries. `postcritic_training_work` and `training_parent_selection_policy` exist.
- Reconciliation fields (`review-reconciliation.json`) match the `:151-167` gates exactly.
- Pycache dirs `D2-retained324-continuation-prepare-luna-20261026-r2/empty-pycache` and `AUDITOR/empty-pycache` exist and are empty.
- Selection, cost, and selected-348 numbers: `candidate_selection` returns 348 (mean 3098.125 > 2939.40625). Cost is `10824.835578584221 + 1131.1351048339857`. Literal assertions match the observer and runner literals.
- Process-liveness helper uses `/bin/ps -p` returncode 1 for absent pids and `os.killpg(pgid, 0)` for groups. The observed pids and pgids match between observer and execution records.

## Nonblocking

Carry-over from r1, status unchanged:

- N2 (r1 medium). Compare-then-`os.replace` TOCTOU at `:703-704`. Documented. Parent must stay sole ledger writer.
- N3 (r1 low-medium). No self-pin of the finalizer. Parent pins its SHA externally before invocation, as the README states.
- N4 (r1 low). Literal receipt fields and counts rather than computed (`:442`, `:453`, `:476`, `:511`, `:636`, `:656`). Backed by earlier checks but not derived.
- N5 (r1 low). Hard-coded `5.399687436876066%` in `report.md` text (`:576`).
- N6 (r1 low). `parent_checkpoint_sha256` vs `continuation_parent_checkpoint_sha256` (`:510`, `:524`) naming is easy to misread.
- N7 (r1 low). Exact float equality against literals (`:333`, `:393-398`, `:416-419`). Deterministic for frozen inputs but brittle. Not evaluated here.
- N8 (r1 info). A crash after `:691` leaves a `.retained348-linear-finalize-*` temp file in the ledger directory.
- N9 (r1 info). `test_finalizer_contract.py:59` hardcodes `/Users/taylor/...`.

New:

- N10 (test coverage, medium). `test_publication.py:111-131` replaces `read`, `sha`, `validate_review_reconciliation`, `_verify_registered_evidence`, `_load_selected_state`, `_check_live_process_absence`. `synthetic_sha` returns the digest for any missing path (`:119`). The 8 CPU controls prove publication mechanics only. They do not exercise any real evidence key, the schedule literal path, or `_load_selected_state`. B1 and B2 both pass the CPU log.
- N11 (low). `os.fchmod` (`:696`) restores mode only. Temp file keeps the process group, and owner/group/ACL/xattrs of the original ledger are not preserved. Ledger is `0600` owned by `taylor:staff`, so no effect today.
- N12 (info). Ledger `state.json` was written at `2026-10-26T20:46:53Z` (15:46 local) with new key `selected348_finalizer_pending` (`status: independent_source_review_pending`). Written during preparation by the parent. Lease unchanged. Not a finalizer defect, noted so the parent knows the ledger was touched before the snapshot logic runs.

## Not verified (limits)

- `.pt` contents not read (binary). Checkpoint-internal values are verified against writer source only.
- Not computed: canonical SHA of an AST-resolved spec, `runner.fingerprint` outputs vs stored fingerprints, the exact learning-rate literal `2.2203389830508478e-05`, `update_progress.complete`.
- The 8 CPU tests were not re-run. Their result rests on `cpu-tests.log`.
- The 13857 registration pins were not hashed individually. Only the count and the 10 `retained324` entries were checked.
- Tracked-file hashes were not recomputed. Prior review (r1) recorded them.

## Recommended next step

1. Do not copy or invoke r3.
2. Fix B1: resolve schedule names against real pinned bytes; move all failable parsing before line 438.
3. Decide B2(a) explicitly: accept a documented weaker binding for `artifact-manifest.json`, or re-audit it. Fix B2(b) by using the audit-binding clause alone.
4. Replace stubs for the evidence and schedule paths in `test_publication.py` and `test_finalizer_contract.py` with fixtures built from the real frozen JSON and the real pinned `lr_schedule.py` bytes.
5. Prepare r4 as a new reviewed preparation directory. Re-run Haiku source review on r4 before any parent invocation.
