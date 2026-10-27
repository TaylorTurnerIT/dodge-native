# D2 best180 all-candidate parent auditor

Read-only auditor for registered run `D2-best180-branch-luna-20261026-r1`. It audits updates 180, 192, 204, 216, 228, 240, and 252 individually. Each published checkpoint must match certificate and sidecar hashes, pass the frozen CPU checkpoint loader and complete-update gate, match registration/config/native/runtime/policy/ancestry identity, local metrics and cumulative counters, and per-slot resume/journal/raw-frame lineage. Duplicate episode index values across slots are valid.

Each evaluation must contain the registered 64 D seeds, correct mean and canonical Q1/Q4 statistics, death/cap accounting, objective, competence predicate, and provisional flags. The candidate ranking uses strictly improved audited mean alive raw frames. Update 180's re-saved model is not authority for the original parent file; the external original checkpoint and accepted receipt hashes remain pinned.

When the full run has ended successfully and all seven immutable certificates exist, run from workspace root:

```sh
python3 learning/runs/v2/D2-best180-all-candidate-auditor-luna-20261026-r1/audit_candidates.py --output learning/runs/v2/D2-best180-all-candidate-auditor-luna-20261026-r1/audit-result.json
```

This writes a proposed result only. Full terminal checks call the frozen `execute_once.validate_outputs`; acceptance still needs parent terminal review. During training, any use against published snapshots is provisional and cannot authorize replacement, continuation, or whole-run acceptance. Missing/partial files reject the audit. Training launcher, source, lease, and output are untouched.

Focused controls: `python3 -m unittest -v learning/runs/v2/D2-best180-all-candidate-auditor-luna-20261026-r1/test_audit_candidates.py` (5 passed). Tests mutate synthetic metadata derived from the frozen registered schema; they write no checkpoints. A read-only attempt to load current update 180 via host Python failed because the registered macOS extension cannot load here; exact error is retained in `runtime-inspection-failure.log`.
