# Critic restoration audit (static, read-only) — r1

Scope: `critic-diagnostic-runner-prepare-20261025-r2/{runner.py,execute_once.py,test_contract.py}`, frozen `python/dodge_rl/checkpoints.py`, pinned torch 2.14.1 source under `python/.venv/.../torch`, `critic-diagnostic-parent-prepare-20261025-r1/parent-terminal-audit-r1.json`, `critic-diagnostic-D2-20261025-r1/worker-result.json`. No tests, no experiments, no checkpoint decoding, no r3 directory read.

Known comparator defect (not re-reported as new): `runner.py:195` type-tags `OrderedDict` vs `dict`.

## Findings

### 1. P2 — failure receipt drops equality components (demonstrated)
- Path: `runner.py:306-309`; `worker-result.json` has no `equality` key.
- Trigger: any component mismatch (model, Adam, or RNG) at entry restoration.
- Consequence: only `"D1 state restoration differs"` is recorded. The `save(entry-restoration.json)` at `runner.py:310` runs only on success, so no per-component evidence exists after a failure. The parent audit confirms this gap (`limitation` field).
- Fix direction: compute `equality` into a variable visible to the `except` path, record it in `result` before `need(...)`, and record per-component digests of both sides (not just booleans).

### 2. P2 — no test covers fingerprint semantics (demonstrated by grep)
- `test_contract.py` has no reference to `fingerprint`, `equality`, or `restore`. The grep returned only guard/worker-result tests (lines 64, 151–259).
- Consequence: the type-tag defect passed the contract suite. Corrected comparator needs:
  - positive: `dict` vs `OrderedDict` with equal keys/tensors → equal;
  - negative: one tensor with one changed byte, one changed shape, one changed dtype, one missing key → unequal;
  - negative: non-tensor leaf type change (e.g. `int` vs `float` with equal `repr`) → must still be decided by a rule that is stated, not accidental.

### 3. P3 — restored optimizer hyperparameters are adopted from the checkpoint (source, optimizer.py:1031-1041)
- `update_group` copies saved `param_groups` over the constructed ones (`new_group` keeps only `params`/`param_names` from current).
- Consequence: `fingerprint(optimizer.state_dict()) == fingerprint(parent["optimizer"])` cannot detect a mismatch between the constructed Adam (`lr`, `eps` from `PPO`) and the checkpoint's group values. It is therefore a weaker check than it looks for the hyperparameter component.
- Not a launch blocker if the parent was trained with the same `PPO` values (the transition validator checks config). Recommend an explicit pre-load comparison of constructed `param_groups` against `PPO` as a separate, non-weakening check.

### 4. Hypothesis — Adam `step` device/dtype (needs rehearsal, low risk)
- `optimizer.py:813-815`: `step` is not cast unless `fused`/`capturable`; other state tensors are cast to `param.dtype`/`param.device` (MPS).
- Fingerprint calls `.detach().cpu()` on tensors, so device placement alone should not change digest. Byte equality is expected. I did not read the non-`step` cast branch in full.
- Rehearsal needed: confirm `restored.state_dict()["state"][i]["step"]` byte-equals parent after load on MPS. Do not run it under this audit.

### 5. Hypothesis — RNG capture side effects (needs rehearsal)
- Static read: `capture_rng` (`checkpoints.py:22-28`) calls `random.getstate`, `np.random.get_state`, `torch.get_rng_state().clone()`, `torch.mps.get_rng_state().clone()`. No draws are made, so no stream advance is expected.
- Not verified: `torch.mps.get_rng_state` side effects on the MPS generator. The `before == after` guard at `runner.py:327-343` would catch a side effect at evaluation time, but not the entry comparison's own capture. Rehearsal: call `capture_rng("mps")` twice and compare.

### 6. No finding — tensor byte/shape/dtype preservation
- `_cpu_copy` (`checkpoints.py:45-47`) uses `detach().cpu().clone()`. `fingerprint` hashes `dtype`+`shape`+`tobytes()` after `.contiguous()`. Equal logical tensors hash equal regardless of stride or device. No defect found.

### 7. No finding — `restore_learner` strictness
- `model.load_state_dict(..., strict=True)` accepts both `dict` and `OrderedDict`. The only failure source is the comparator, as the known defect states.

## Not a blocker found
- `Adam.load_state_dict` representation change: the `optimizer.state_dict()` top level is a plain `dict` on both sides; `state` values are dicts of tensors. Type-tag mismatch is not expected there, but this is by reading only. Rehearsal would settle it.

## Summary
Blocking defects beyond the known comparator: none demonstrated. Demonstrated gaps: #1 (telemetry), #2 (test coverage). Hypotheses needing rehearsal: #4, #5. Advisory: #3.
