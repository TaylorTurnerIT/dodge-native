# Retained324 linear auditor r2 review (r1)

Reviewed: `learning/runs/v2/D2-retained324-linear-auditor-prepare-luna-20261026-r2/` (frozen), with producer reads of `D2-retained324-linear-integrated-luna-20261026-r4/` (`runner.py`, `execute_once.py`, `registration-final-r2.json` pins/keys only, `lr_schedule.py`) and `D2-retained324-linear-execution-observer-parent-20261026-r1/observe.py` (source only). Precedent: `D2-retained324-linear-auditor-review-haiku-20261026-r1/report.md`.

Not read: current scheduled trial outputs, lease/state, checkpoints, `observation.json`/`execution-result.json` from any run, `D2-retained324-linear-lr-20261026-r1/`. No code executed, no tests run, no subprocess for runtime. Hashing and `grep`/`diff`/`Read` only.

## Verdict

Most r1 findings are fixed in the actual call paths. One new MEDIUM gap remains: the replacement `check_import_cache` drops the registration's own `import_policy` check. No CPU-evidence blocker found. Binding freeze is not blocked by the items below except as noted, but finding 1 should be fixed or explicitly accepted before the parent writes `audit-binding.json`.

## r1 finding status (checked on call path)

| r1 | Status | Evidence |
|---|---|---|
| HIGH 1 binding unhashed | Fixed | `wrapper.load_binding` (`wrapper.py:86-92`) and `audit_candidates.load_frozen` (`:224`) both compare `binding_digest(raw, expected_binding_sha256)` before `json.loads`. Parent-supplied digest is required (`binding_digest` raises when missing/malformed). `binding_sha256` recorded in wrapper record (`wrapper.py:349`) and auditor result (`audit_candidates.py:733`), both from the verified digest. |
| HIGH 2 self-computed source pins | Fixed | `binding_builder.py:103-106` compares each of five sources to `frozen-manifest.json` `auditor_sources`; `:107-110` requires reviewed assembly to bind same values. Wrapper/auditor recheck disk digest against binding (`wrapper.py:101-102`, `audit_candidates.py:234-236`). |
| MED 3 unpinned schedule imports | Fixed | `audit_candidates.load_bound_schedule_modules` (`:184-197`) loads `lr_schedule` then `schedule_contract` via `load_pinned_module`, sets `sys.modules`, then checks `__file__` and `schedule_contract.lr_schedule is lr_schedule`. Import order is correct (`lr_schedule` before `schedule_contract`). |
| MED 4 constants overwritten | Fixed | Constants kept (`audit_candidates.py:42-48`); registration compared to them (`:276-281`, `:143-152`). `load_frozen` declares them `global` but does not assign. |
| MED 5 instantiation pin dropped | Fixed | Builder checks instantiation bytes at `binding_builder.py:87-96`; `audit_candidates.py:244-246, 680-683` check digest and path. Observer source digest checked at `wrapper.py:125`, `audit_candidates.py:676`. |
| LOW 6 terminal JSON read twice | Fixed | `audit()` returns parsed `_terminal_records` (`:754-792`); wrapper's `terminal_gates` consumes those same objects (`wrapper.py:331`). Digests tracked and rechecked (`:799-800`). |
| LOW 7 relative observer path | Fixed | `audit_candidates.py:241` checks absolute; builder checks absolute (`binding_builder.py:62-66`). |
| LOW 8 `verify_frozen_manifest` schema | Fixed | `lr_schedule.py:117-127` now reads v2 `files`/`auditor_sources`. Only caller is `test_schedule_contract.py:68`. |
| LOW 9 horizon not bounded | Accepted design per user | `validate_schedule_state` still unbounded; auditor fails closed via `validate_checkpoint_schedule` (`local 0..60`, `schedule_contract.py:51-52`). Not counted. |
| LOW 10 non-dict counters | Fixed | `check_saved_lr` (`audit_candidates.py:374-377`) checks `isinstance` before `.get`. |
| LOW 11 full-mode guard convention | Partly unchanged | In-process `audit(provisional=False, ...)` still callable (`audit_candidates.py:659`). Wrapper full mode requires binding and observer dir, so impact stays limited. |
| LOW 12 test coverage | Partly improved | 24 tests claimed; not rerun. Coverage of `check_saved_lr` and `load_frozen` still source-level. |
| LOW 13 float equality | Unchanged | Helper-only LR constraint noted; no action required beyond r4 contract. |

Helper math: `diff` of PREP `lr_schedule.py` (`ef81…`) vs OWN (`1ac2…`) differs only in docstring and `verify_frozen_manifest`. Schedule math is identical. No math drift.

## Findings

### 1. MEDIUM — registration `import_policy` never checked; replacement lambda drops it

- Path: `audit_candidates.py:289-294` (replaces `runner.check_import_cache`, installed before `runner.load_registration` at `:295`). Original `runner.py:245-252` checks `reg["import_policy"]["pycache_prefix"]` equals env and `sys.pycache_prefix`, and that it is an empty dir.
- Trigger: any run where registration `import_policy.pycache_prefix` differs from `OUT/empty-pycache`. Registration (`registration-final-r2.json:95-98`) declares `…/D2-retained324-continuation-prepare-luna-20261026-r2/empty-pycache`, not this OWN directory.
- Consequence: the lambda checks only `OUT/empty-pycache` and the wrapper checks the same path. The registration-declared prefix is never enforced on the auditor path, while `runner.load_registration` (`runner.py:517`) reaches the replacement and passes silently. The registration digest is pinned, so content is fixed, but the invariant is quietly weakened. Impact on evidence is LOW (the audit launches no worker; `execute_once.py:354` uses the registered prefix only for the worker), but it violates "independent preflight preserved."
- Fix: in the lambda, also assert `reg["import_policy"]["pycache_prefix"]` equals the env prefix and `OUT/empty-pycache`, or keep the original runner check and do not replace it. Alternatively state explicitly that the registered prefix is intentionally not enforced for the auditor.

### 2. LOW — terminal and observer JSON not externally pinned

- Path: `audit_candidates.py:754-766` (`execution-result.json`, `worker-result.json`, `observation.json`); `wrapper.py:331-332`.
- Trigger: any rewrite of those three files before audit, with the same schema.
- Consequence: digests are recorded in output (`terminal_record_sha256`, `tracked_file_sha256`) but no external digest is in the binding. r1 finding 5 asked for `observation.json` pinned; it remains self-derived. Parent-owned records, so LOW.
- Fix: put expected digests for these three in the binding or parent acceptance record, same as the observer instantiation.

### 3. LOW — bootstrap does not check Dodge origins after runner load

- Path: `bootstrap_readiness.py:19-34` (no `check_loaded_dodge`/`reject_preloaded_dodge` after `auditor.load_frozen`), vs `wrapper.py:312-317` and `audit_candidates.py:329-333` in audit path.
- Consequence: a readiness pass does not show runtime origins were pinned. Full audit still checks them, so this is a readiness-fidelity gap only.
- Fix: call `wrapper.check_loaded_dodge(loaded_reg, runtime, members)` in bootstrap after load (only if loading runner imports `dodge_rl`; not verified without running).

### 4. LOW — `load_binding` re-reads binding twice inside wrapper and auditor separately

- Path: `wrapper.py:90-91` (read compare) and `audit_candidates.py:223-225`. Each read is checked against the same expected digest, so consistent. Not a defect; recorded for completeness.

## Call-path validation (producer keys, read-only)

- `observe.py` writes every key read by `wrapper.terminal_gates` and `owned_processes_absent`: `outer_raw_exit`, `worker_raw_exit`, `first_event`, `launch_count`, `success_authoritative`, `outer_inclusive_wall_seconds`, `outer_limit_seconds`, `max_aggregate_rss_bytes`, `aggregate_rss_limit_bytes`, `mps_limit_bytes`, `postflight{lease,pins,cache_empty_after,publication_failure_absent}`, `outer_process_absent`, `worker_process_absent`, `worker_group_absent`, `observer_pid`, `outer_pid`, `outer_process_group` (`observe.py:170-309`).
- `execute_once.py` writes `status`, `actual_worker_launch_count`, `observed_worker_raw_exit`, `worker_pid`, `owned_pgid` (`:328-443`). `worker["peak_rss_bytes"]`, `peak_mps_driver_bytes`, `first_failure` are read; worker producer not re-verified here.
- `runner.load_registration` returns the same dict as `validate_registration(read(path))`, so `reg == json.loads(REG_PATH)` holds and the strict import wrapper's equality check (`wrapper.py:214-215`) holds.
- `pins` count: registration has 13857 pins (`audit_candidates.py:140`); `observe.py:305` hard-codes 13857; consistent.
- `observation["outer_process_group"]` may be `None` (`observe.py:184`); auditor requires `int` (`audit_candidates.py:771`), so full mode fails closed rather than passing. Intended.

## Limits

- Not verified: runner `worker` result fields and `validate_outputs` internals beyond key names.
- Not verified: `parent_adapter.py`, `registration_schema.py` function bodies beyond import-path checks.
- Not verified: whether `runner.load_registration` imports `dodge_rl` (would change finding 3). Requires reading `runner.py:446-519` callees; not run.
- Not verified: 24 CPU test results (cited from `cpu-tests.log`; not rerun).
- No binding was built, no audit run, no checkpoints loaded, no lease/state read.

## Hashes (read-only, recomputed)

| File | sha256 |
|---|---|
| `audit_candidates.py` | `ce707de1e50e1757cd34796ff18e303ff4e71618c9c4d30469f100112f2948b6` |
| `binding_builder.py` | `30dab9bd2369b7109c700296f5610206504bf60d28af4e412d0d1a3739fe69af` |
| `bootstrap_readiness.py` | `f18a4996bd87b7e6f79e2dd83f21c2c7cafdde4a80aeee437bdc40283ec0c7c4` |
| `lr_schedule.py` | `1ac2a62de4989c30415cd4167262456299deae7cc7a7fbffc2d532ba4a8f09eb` |
| `schedule_contract.py` | `efaa421a3babbfd995074ae86c26731350d614dff7fdd34cefd4463e4cdf7809` |
| `wrapper.py` | `871bed65a8cc207c93bc6b5d77fd87ec0e78f6619273c52ce7c57446e96a3e2e` |
| `frozen-manifest.json` | `9a732cff4646610b62ff399d01837fddf81199f698493bd997bc0b33a321b74c` |
| `review_assembly_contract.json` | `f9876283ec44ff6c6cd5e4cdcdd197a96b1b8c9a59ebfb6d19ba7377678e3a3b` |
| `report.md` (prep) | `4384eeeb34310c2ecc321d06155702d02b2a1247fbac8cc6f054b51a36c6e048` |
| `cpu-tests.log` | `6abd8762cb13e46a6422a349c93f9c331c5f7dbedbe7441b6182c4d3bfbbfa06` |
| `observer observe.py` | `f271b2641b995fc34a90cebe420657953cb16ce9038886edc2fd74c184ccacad` |
| `registration-final-r2.json` | `0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e` |

Note: `output-manifest.json` in the prep dir hashes to `48d12e2a…`, not the value recorded in its own manifest (`d86d0cd2…`). Recorded self-hash in prep `output-manifest.json` is stale for the file on disk; prep's `files` map lists `report.md` etc. but not itself, so this is a manifest-freshness note only.

## Requested fixes before parent freezes binding

1. Decide finding 1: enforce the registration's `import_policy.pycache_prefix` in the lambda, or document that it is intentionally not enforced for the auditor.
2. Pin `execution-result.json`, `worker-result.json`, `observation.json` digests externally (finding 2).
3. Optional: add dodge-origin check after `load_frozen` in bootstrap (finding 3).
