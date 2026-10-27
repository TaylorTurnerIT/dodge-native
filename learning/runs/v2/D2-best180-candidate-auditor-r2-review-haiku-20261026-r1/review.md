# D2 best180 candidate auditor r2 — read-only review (haiku, r1)

Scope: frozen `learning/runs/v2/D2-best180-all-candidate-auditor-luna-20261026-r2/` (`audit_candidates.py` sha256 `26d1e21c…d999d90f`, tests `5a7b8719…3603…6036`), checked against the r1 parent-launch scope in `D2-best180-branch-parent-launch-20261026-r1/review-reconciliation.json` and the r1 defect list. CPU-only static read. No runs, no checkpoint reads, no writes outside this directory.

## Verdict

No blocking findings for the read-only provisional mode. Full terminal mode should not be used as parent authority until findings 1–3 are fixed in a successor (frozen r2 cannot be edited). None of the findings selects or accepts a candidate.

## r1 defects — status

- `identity.config_sha256` invented key: closed. Uses `ident["config"]` (lines 51, 170).
- Always-clear proposal when entry180 equals original: closed. `choose_best` requires strict `>` over original (lines 69–71, 221).
- Sibling runner import unbound: closed. `bind_frozen_runner` pins `runner.py` by file origin and sets `sys.modules["runner"]` before `execute_once.py` loads (lines 31–37, 94–95). Pinned source hashes match the reconciliation (`runner.py` 8807b520…, `execute_once.py` cd15ee2b…).
- `run-result.json` lookup: closed. Reads `execution-result.json` (line 230).
- Default `hostpython3` cp312 load: partially closed. Only README instructs the pinned `python/.venv/bin/python`; the code does not enforce it (see finding 1).

## Findings

1. **Full mode does not enforce `-B` or the registered `PYTHONPYCACHEPREFIX`** (`audit_candidates.py:28–29, 95, 109, 159, 252`). Impact: running without the README invocation makes `load_module` and `dodge_rl` imports write `__pycache__` into the frozen prepare tree and the runtime tree. Those new files are not in `runtime-member-inventory.json`, so the source/runtime immutability claim is weakened and the audit output is no longer reproducible from the frozen tree. Fix: in `audit()` when `provisional` is false, require `sys.flags.dont_write_bytecode` and `os.environ["PYTHONPYCACHEPREFIX"]` equal to the registered prefix, otherwise raise.

2. **Ranking baseline is unpinned and not cross-checked** (`audit_candidates.py:220–221`). Impact: `original_eval` is read from `development-000180.json` without a hash pin. A changed or mismatched baseline changes `proposed_best_update` silently. The auditor also never checks `certificates[180]["mean_alive_frames"]` against that baseline, although entry180 is a re-save with identical model/Adam/RNG (line 175–176) and should evaluate to the same mean. The real snapshot shows entry180 at `1854.46875`, which would satisfy such a check now. Fix: pin the baseline file's SHA and require equality for update 180.

3. **Certificate identity fields are not bound** (`audit_candidates.py:137–139, 217`). Impact: only `cert["checkpoint"]` and `cert["checkpoint_sha256"]` are checked. The runner writes `phase_update` and `local_update` into each development certificate (runner.py:660). A certificate with mismatched update numbers would pass if its checkpoint hash matched. Low risk because the checkpoint hash binds it, but it is an unverified field. Fix: check `cert["phase_update"]==update` and `cert["local_update"]==update-180`.

4. **Module origin not asserted for `dodge_rl` imports** (`audit_candidates.py:109, 159`). Impact: `checkpoints` and `identity` are imported after `sys.path.insert(0, runtime)` but their `__file__` is never checked, and the native extension origin is not checked either. The runner does check `dodge_rl.__file__` (runner.py:563) and native parent (runner.py:140), but the auditor does not. Current risk is low in a fresh process, but a pre-imported `dodge_rl` would pass. Fix: assert `Path(ckpt.__file__).resolve()` and `identity.__file__` are under `runtime/dodge_rl`.

5. **Competence and objective constants are duplicated, not bound** (`audit_candidates.py:200, 214`). Impact: the auditor hardcodes `3060` and the objective formula `score + .01*alive − 5·terminated`. If runner constants change, the auditor silently disagrees instead of failing. Fix: reference `runner` constants or the `runner.performance` output.

6. **Output overwrite refusal is check-then-write** (`audit_candidates.py:252–253`). Impact: small TOCTOU window. Fix: open with mode `"x"`.

7. **Provisional reads fail closed mid-append, not on a stable prefix** (`audit_candidates.py:23–26`). Impact: `stable_lines` raises when the last journal or metrics line is incomplete. This is not a false pass, but a provisional run during active training can error repeatedly. The prefix logic (lines 120–126, 186) only trims certificates, not journals. Fix: in provisional mode, truncate to the last newline-complete line and hash that prefix.

8. **Minor dead or vacuous code** (`audit_candidates.py:123, 136, 218`). The `.partial` clause tests names that never end in `.partial`; the first `choose_best` call at line 218 is overwritten at 221; `exact_tree` falls back to `a==b` for tensors if torch import fails (line 77–80), which fails closed for multi-element tensors. No correctness impact.

9. **Informational, not a defect**: ranking ignores `competence_passed`. The spec says "highest strictly improved audited dev mean only", and the code matches that. A proposed candidate may still fail the 3060 competence predicate. Parent acceptance must check it.

## Items checked, no finding

- Parent abandoned frames: excluded from `complete` (line 192) because only `kind=="completed"` is summed; inherited records are stripped by `runner.validate_episode_journal` (runner.py:515). Local abandoned frames are added at line 193.
- Full-mode terminal path: `launcher.validate_outputs(reg, worker, REG_SHA)` matches the frozen signature (execute_once.py:64). Launcher emits only `"passed"` or `"failed"` in `execution-result.json`, so the `("passed","completed")` allow-list is broader than needed but harmless.
- Stable reads of checkpoints: hash checked before and after `load_checkpoint` (lines 142–143); tracked files rehashed at the end (line 242–246).
- Duplicate per-slot episode indices: no cross-slot uniqueness gate, as specified.

## Not verified here

No checkpoint was read. Behavior of the frozen auditor was not re-run; focused tests and the provisional result are taken from the frozen receipt, which I hashed but did not re-execute.
