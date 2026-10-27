# Parent-callable terminal auditor preparation

`auditor.audit(registration_path, externally_pinned_registration_sha256, raw_supervisor_exit, output_dir_for_new_parent_receipts)` performs static terminal reconciliation only. It imports no Torch, game, native environment, checkpoint, or training modules. It does not launch work, retry, clear leases, alter markers, write ledgers, or choose/promote candidates.

Before reading `confirmation.json` or either result file, it checks registration bytes, outer receipt identity and raw worker exit/wall/stage/candidate/cohort and artifact byte/SHA bindings, claimed marker identity, final worker heartbeat identity and positive RSS/MPS caps, independent `ps` absence, cancellation absence, exact lease/no conflicting legacy leases, registered empty bytecode cache, root README SHA, and registered sources, 13 runtime members, six checkpoint/source-receipt pairs, three cohort manifests, review records, runtime executable, accepted benchmark receipt, and adapter pins. The final registration must provide `root_readme_path`, `root_readme_sha256`, and a final outer receipt/heartbeat matching the reviewed launcher contract. `raw_supervisor_exit` is the independent caller argument; outer `raw_exit_code` records worker exit. Parent freezes these fields and all pins.

Then it validates the ordered 324/348 bundle against `confirmation-winner.json` and `confirmation-incumbent-348.json`, compiles the adapter from one hash-checked source buffer, builds the terminal audit in memory, and calls `analyze` with pinned bytes. It persists `audit.json`, `statistics.json`, and a SHA-linked `receipt.json` only after adapter validation and recomputed performance matches both declared summaries. Eligibility is `eligible` or `inconclusive`; it carries no promotion or ledger authority.

Run with project Python 3.12 and bytecode disabled:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -m unittest -v learning.runs.v2.confirmation-terminal-auditor-prepare-luna-20261026-r1.test_auditor
```

The process snapshot uses system `ps -axo pid=,ppid=,pgid=`. Registered empty `pycache_prefix` must already exist. Tests use synthetic CPU-only data and do not establish runtime qualification or any confirmation outcome.
