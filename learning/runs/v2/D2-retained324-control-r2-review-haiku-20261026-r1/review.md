# D2 retained324 control prep R2 review (Haiku, static)

Scope: `learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/`. Static reads, diffs against R1, and sha256 only. No imports, tests, decoding, MPS, env, training, lease, state, or source changes. Parent replay (`D2-retained324-control-parent-validation-20261026-r2/`) and observer (`D2-retained324-execution-observer-parent-20261026-r1/`) were not reviewed beyond existence and hash checks. This review carries no launch-qualification or acceptance authority.

Full hashes and provenance: `receipt.json`. Structured findings: `review.json`.

## Verdict

No blockers. R1 F1 (stale `parent_run_id`) is fixed. R1 F3 (launch command) is recorded, but the recorded command is stale (see new finding N1). R1 F2 and F4 carry forward unchanged as low.

## Checked and passing

- Diff vs R1 prep: `runner.py` differs only at `FINAL_SOURCE_DIR` (line 30) and line 738 `parent_run_id` (now `D2-retained300-continuation-20261026-r1`, which is the parent checkpoint's run). `execute_once.py`, `parent_adapter.py`, `registration_schema.py` are byte-identical to R1.
- Hashes match the brief and registration fields: runner `43e93f74…0c10`, launcher `7215ae66…2310e`, adapter `355880c2…a26a26`, schema `87497edeb…7f57f`, registration `44ac8185…34cd5a`.
- Pin sets (parsed from `registration.json`): R2 has 13846 pins. R1 (13827) and working r5 (13827) are both subsets of R2. Zero removed, zero value changes on shared keys. Added vs R1 = 19: 15 historical r5 pins R1 had dropped, plus the 4 R2 source paths.
- Recomputed sha256 of all 15 restored historical pins: 0 mismatches. Recomputed the 4 R2 source paths: match.
- Pinned `runtime_sha256` `2cf10e9f056f41b39dc17845192e9adf553a5f699546d4f5dcea764a23e36b31`, config `1c24df3e…`, native new `022d41dd…`, native old `967c7249…`, parent registration `8a60dc80…`. Values consistent in registration.
- Parent aliases in `parent-assembly.json`: completed receipt `b170f68c…`, decision `58f167f4…`, worker result `9345be58…` recompute to the recorded values. Upstream receipt `d64d0f80…` is recorded, not checked against a pin.
- Limits: planned 1750, work 1790, total 1800, cleanup 10, RSS and MPS each 6442450944 (6 GiB), retries 0, max_updates 60, eval `[324,336,348,360,372,384]`, run_seed 4200000001, `forbidden_outputs` declares `lr-transition.json`.
- Empty cache dir `empty-pycache/` exists and is empty.
- `validate.py` first attempt failed on bytecode policy before any mutation (`validation-attempt-01.log`). Corrected rerun recorded in `validation.json`. Not re-run here.

## Findings

1. **Low, new (N1): stale launch command.** `launch-command.json` (sha `dcbbc4b9…`) has 0 occurrences of `--registration-sha256`. Trigger: someone runs the recorded command verbatim. Consequence: argparse rejects it before any claim or write, so no harm, but it wastes an attempt. The parent reports that the observer `D2-retained324-execution-observer-parent-20261026-r1/parent-command.json` is the authoritative invocation and includes the flag. Fix the runbook record, not the code. No refreeze needed. I confirmed the flag is present in `parent-command.json`.
2. **Low, new (N2): weak preparation check.** `validate.py` (sha `c84e38e2…`, not pinned) checks `candidate_parent_run_id_matches_selected_receipt` with a substring search for `"parent_run_id": "<run_id>"` in `runner.py` text. Trigger: the literal appears anywhere in `runner.py`. Consequence: check can pass without the state field being correct. Not runtime-enforced. Preparation-only; not launch-blocking.
3. **Low, carried (R1 F2):** `execute_once.py` still uses `mkdir(exist_ok=True)`. Parent observer absence gate covers it. Inherited, byte-identical.
4. **Low, carried (R1 F4):** `forbidden_outputs` (`lr-transition.json`) still not runner-enforced. No writer exists.

## Not verified by this review

- Parent replay `validation.json` and `replay-receipt.json` contents (existence only, not read).
- Observer `observe.py` logic and `instantiation.json` constants. Only its hash `1f991a9a…71f` was taken.
- Actual live execution, lease, or outputs (none exist; none expected).
- The 13827 R1-shared pins were not recomputed here. Relied on R1's recompute plus zero value changes on shared keys.
