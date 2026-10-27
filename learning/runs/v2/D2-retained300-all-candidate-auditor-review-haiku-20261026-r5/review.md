# Retained300 all-candidate auditor review (static, read-only)

Target: `learning/runs/v2/D2-retained300-all-candidate-auditor-luna-20261026-r5/`
Reviewer: claude-haiku-5-5 (self-reported). Static read and hash only. No imports, tests, MPS, training, lease, ledger, or source writes. No current RUN outputs read.

## Verdict

No blockers. No actual full-mode crash found by static key and signature matching. Full run remains parent-gated as specified.

## Findings

| Severity | Location | Finding | Trigger | Consequence |
|---|---|---|---|---|
| low | `audit_candidates.py:369` | `validate_observer_instantiation` is never called; only the instantiation digest is checked (`:514-515`). | Full mode with pinned `instantiation.json`. | Latent. Schema and `actual_launches==0` are not enforced in code. |
| low | `observe.py:184` → `wrapper.py:219` | `outer_process_group` is `None` if the outer pid is missing from the snapshot at launch; `os.killpg(None, 0)` raises `TypeError`. | `process_rows()` has no row for `proc.pid` right after `Popen`. | Full-mode exception before `full-audit.json` is written. No state damage. Unlikely. |
| low | `wrapper.py:280` | Output is opened with `"x"` before `json.dump`. A serialization error leaves a truncated exclusive file. | Non-JSON or NaN value in record. Finite checks make this unlikely. | Blocks retry until manual removal. |
| info | `audit_candidates.py:242-243` | Duplicate `len(metrics)` check; docstring placed after a statement. | Always. | Cosmetic. |

## Checked and consistent

- Pinned digests match all listed files (see `receipt.json`).
- Registration pin count 13827. `forbidden_outputs` is `[lr-transition.json]`. No old 7-candidate or 137xx pin constraints. Candidates 300/312/324/336/348/360 match the registration.
- Observer field names used by `wrapper.terminal_gates` and full-mode `audit()` exist in `observe.py` with matching names. `observation.json` is written to the same directory the wrapper reads.
- Execution fields (`actual_worker_launch_count`, `observed_worker_raw_exit`, `status`, `worker_pid`, `owned_pgid`) are set in `execute_once.py:331-332` and saved at `:397`.
- `validate_outputs(reg, worker, registration_sha)` exists at `execute_once.py:88`. `import runner as r` resolves to the module the auditor installs.
- Runner checkpoint keys match what the auditor reads. The two clock baselines stay distinct. The wall formula is checked at `audit_candidates.py:329-330`.
- Checkpoint API calls match `python/dodge_rl/checkpoints.py`.
- Entry abandoned records are excluded from completed-frame conservation, consistent with `runner.py:741-743` and `:827`.
- CLI refuses full mode. Full mode requires the registered observer directory.

## Limits

- Not read: `runner.load_registration` body, `validate_gradient_alignment`, and metric-row readers. Metric keys are inferred from writers.
- Not read: most of `validate_outputs`; its return value is assumed JSON-safe.
- Not read: `dodge_rl.dev_eval` and episode-row sources.
- No runtime execution. Crash-freedom rests on static matching only.
- Entry raw-frame conservation depends on runtime abandoned `gameplay_frames`, which needs the checkpoint to confirm.

## Recommendation

No repair round needed for the findings above. Proceed with parent-only full mode after observer, worker, and outer processes are absent, as in `future-parent-full-mode.md`.
