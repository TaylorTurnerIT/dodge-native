# D2-retained348 finalizer r4 review (Haiku 5.5, `claude-haiku-5-5`)

Scope: source-only review of `learning/runs/v2/D2-retained348-linear-finalizer-prepare-parent-20261026-r4/` (`finalize_parent.py` SHA-256 `49b40030113fe77dee8c59dc91ff7ea7721fa9d7ad414ccbfefe1d7c0ff95567`, matches `preparation-manifest.json` `source_sha256`). Prior review: `D2-retained348-finalizer-r3-review-haiku-20261026-r1/report.md`.

Method: read `finalize_parent.py`, three tests, README, manifest, `cpu-tests.log`; `diff` r3 vs r4; read-only `shasum`, `jq`, `grep`, `ls` over frozen evidence. No Python imported or run, no tests run, no checkpoint load, no lease or ledger write, no shared edits. Only this directory was written.

## Verdict: NOT CLEAN. One blocker (narrow).

## Blocker

### B1. Failable parsing still runs after the first write

The r4 README says "parse and verify ... before any receipt write". The schedule block now does run before the first write (`finalize_parent.py:420-428` before `_write("finalizer-assembly.json")` at `:448`). The rest of the parsing does not.

- `:590-602`, the six-candidate loop, reads `RUN/development-NNNNNN.json` and indexes `cert["evaluation"]["rows"]`, `row["alive_frames"]`, `row["terminated"]`, `row["death_cause"]`, `cert["evaluation"]["deaths"]`, `cert["evaluation"]["caps"]`. It runs after `audit.json` (`:474`), `completed-iteration-receipt.json` (`:504`) and `retained-best-candidate-receipt.json` (`:570`) are written.
- `:506-531` reads `selected["identity"]`, `selected["identity_sha256"]`, `selected["run_seed"]` after `:448`. Only `counters`, `cumulative_counters`, `inherited_counters`, `next_episode_indices` and the config, runtime, native and policy bindings are checked before the first write. `identity`, `identity_sha256` and `run_seed` are not.
- `:571-573` reads the incumbent certificate. It is pinned in `registration-final-r2.json` (`pins`, `73f9ee…`), so the pre-write loop at `:260-261` already covers it. Not a blocker.

Why it matters: r3 B1 was the same failure class, partial output before a parser fails. Here a `KeyError` or `JSONDecodeError` after `:474` leaves a half-accepted output directory, and the `"x"`-mode writes make a rerun fail.

Likelihood on the frozen inputs is low. The six certificates are hash-bound through `artifact-manifest.json` (`:249-252`), and I confirmed on disk that all six have `evaluation.rows` (64), `complete`, `deaths`, `caps`, and that row 0 has `death_cause` and `alive_frames`. I did not check `death_cause` on every terminated row or the selected checkpoint keys, which are inside a binary `.pt`.

Fix: build `candidate_comparison` and the six per-candidate reads, and read the selected-checkpoint identity keys, before `:438`. Add a control that injects a failure into each read and asserts zero files written.

## Verified

- Exact r3→r4 delta (`diff -u`): manifest check moved to reconciliation hash; observer clause changed to exact path plus SHA from audit binding; schedule block moved before first write; `read_json_from_bytes` replaced with the restricted `ResolveConstants` plus `literal_eval` parser. Nothing else changed.
- Pinned hashes on disk match the constants and manifest:
  - `registration-final-r2.json` `0a6bf98…`
  - `full-audit.json` `e1c32e99…`
  - `audit-binding.json` `a8ad01cb…`
  - `review-reconciliation.json` `4b4e51ed…`
  - Haiku r3 report `7bd06e8f…`
  - auditor `lr_schedule.py` `1ac2a62d…`
  - prep `lr_schedule.py` `ef81e875…`
  - `finalize_parent.py`, `test_publication.py` `93fa7fe6…`, `test_finalizer_contract.py` `7e0656e6…`, `test_real_evidence.py` `bb1aba28…`, `README.md` `a806a9bf…`
- Schedule parser on the real pinned bytes, by reading. Both copies bind `ORIGIN_CUMULATIVE_UPDATE=372`, `HORIZON_UPDATES=60`, `START_LR`, `END_LR` once each before `SCHEDULE_SPEC` (`lr_schedule.py:12-20`). `DECAY_SPAN = START_LR - END_LR` is a `BinOp`, so it is skipped and never referenced. Every `Name` in `SCHEDULE_SPEC` resolves. The restricted parser executes no code: `ast.parse`, `literal_eval`, and a `NodeTransformer` that raises on any unknown `Name`. `open(...)`, `UNKNOWN`, `math.pi`, f-strings, calls, and attribute access all fail closed.
- Observer binding: `audit-binding.json` `observer_source.path` equals `str(OBSERVER/"observe.py")` under `ROOT`. Its SHA `f271b264…` matches the file. `observer_instantiation` `56d547b6…` matches `instantiation.json`. The binding is pinned through `BINDING_SHA`, so this is not weaker than the removed registration-pins clause, which could never pass.
- Artifact manifest: `artifact-manifest.json` SHA `f2dda47a…` equals `artifact_manifest_sha256` in the parent reconciliation. Manifest is flat with exactly the 32 `expected_outputs` keys. Accepted, but it is a parent attestation, not an independent audit (see limits).
- Candidate fields used by the finalizer all exist in `full-audit.json`: `checkpoint_sha256`, `sidecar_sha256`, `certificate_sha256`, `component_fingerprints{model,Adam,RNG}`, `mean_alive_frames`, `performance`. `certificate_sha256` for 348 `f0da1736…` equals the on-disk `development-000348.json`.
- Worker and observer fields used pre-write exist with the expected values: `updates` 60, counters 983040 / 7680, cumulative 432, `peak_*` below limit, `elapsed_seconds` 1127.39, trajectory `6806.37175508199`, `outer_inclusive_wall_seconds` 1131.1351048339857, `launch_count` 1.
- Cost anchor path (`d3ddc427…`) exists and `completed_campaign_resource_cost_after_seconds` is `10824.835578584221`.
- Selection rule and literals: `candidate_selection` picks max mean with earlier-update tie-break. 348 mean `3098.125` exceeds incumbent `2939.40625`.
- Ledger: `active_long_campaign` equals `reg.expected_lease` exactly. `active_inference_diagnostic`, `active_inference_campaign`, `active_inference_lease`, `cancel_requested` are null. Cancel file absent. `state.json` mtime is 15:56, after r4 prep at 15:53 (matches r3 N12).
- Test controls: `test_real_evidence.py` exercises real `_verify_registered_evidence` and real schedule bytes. `test_publication.py` stubs only the evidence and state loaders and runs real publication and atomic commit.

## Nonblocking

- N1 (low, latent). `read_json_from_bytes` `constants` is not cleared when a name is rebound to a non-literal, which the `except` branch at `:741-744` skips. Also not tracked: `AugAssign`, `AnnAssign`, `import`, `for`, and duplicate `SCHEDULE_SPEC` (first wins, runtime uses last). A stale literal could then resolve to a value the runtime never uses. Pinned bytes do not contain this pattern, and `:425` pins the helper SHA, so it is not reachable today. Fix: pop or poison any top-level-rebound name; reject duplicate `SCHEDULE_SPEC`.
- N2 (low). `identity_hash` is imported at `:310` and never used. `identity`, `identity_sha256`, `run_seed` go into the receipt unchecked. Either recompute `identity_hash(selected["identity"]) == selected["identity_sha256"]` pre-write, or drop the import. Not executed here, so the signature is unverified.
- N3 (test gap). No control injects a failure after the first write. No control covers rebinding or duplicate `SCHEDULE_SPEC`. `test_publication` stubs `_verify_registered_evidence` and `_load_selected_state`, so the ordering property is unexercised.
- N4 (test gap, carry-over). `test_finalizer_contract.py:59` hard-codes `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79`.
- N5 (carry-over from r1/r3). Compare-then-`os.replace` TOCTOU at `:688-705`; parent must remain sole ledger writer. Temp file leak on exception at `:692` (N8). `fchmod` restores mode only, not owner, group, ACL, or xattrs (N11).
- N6 (info). `sys.dont_write_bytecode = True` is a global side effect on import, though import remains otherwise inert.

## Not verified (limits)

- `.pt` contents not read. Checkpoint-internal values are verified against writer source only (carry-over).
- `canonical_sha` of the parsed spec not computed. Its equality to `7ceed85c…` rests on the r4 real-evidence test in `cpu-tests.log`, not on this review.
- Cost sum `11955.970683418207` and trajectory sum not recomputed here; carried from r3.
- Artifact manifest and its 32 hashes are trusted through the parent reconciliation, not through independent audit. Parent should document this weaker binding.
- No tests were run, per constraints. `cpu-tests.log` (`84af1229…`) is taken as reported.

## Recommended next step

1. Fix B1: move the six-certificate loop and the selected-checkpoint identity reads before `:438`, and add failure-injection controls showing zero writes.
2. Resolve N2: either check `identity_hash` pre-write or remove the import.
3. Optionally fix N1 and add rebinding and duplicate-spec controls.
4. Prepare r5 as a new reviewed directory. Re-run Haiku source review before any parent invocation.
