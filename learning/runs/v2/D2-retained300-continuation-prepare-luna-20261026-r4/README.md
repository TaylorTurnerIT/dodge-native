# D2 retained300 continuation preparation R4

Status: CPU/source-only selected-parent preparation. Phase300 checkpoint is sole model, Adam, RNG, counter, and resume authority. External terminal receipt grants continuation authority. Checkpoint sidecar remains provisional. Completed-iteration receipt supplies resource-cost clock only.

`runner.py`, `preflight_prepare.py`, and `execute_once.py` are preparation-only and perform no environment construction, marker claim, registration, lease, or worker launch. The execute entry validates parent first. The exact selected checkpoint and receipts are read-only. R3 parent validation helper is integrated unchanged.

Limits prepared: 60 updates from phase300 to360; evaluations at 300/312/324/336/348/360; cumulative updates348 to408; maximum7680 optimizer steps and983040 decisions; planned1750s, work1790s, outer1800s including10s cleanup;6GiB RSS and separate6GiB MPS limit. New launcher T0 starts future deadlines.

Seed proposal is 4200000000. A source scan found no collision among 16 recorded run_seed values, but no authoritative seed ledger was present. Candidate remains unreserved and needs parent confirmation. Remaining parent-controlled work: confirm candidate against authoritative ledger; finish complete registration/pins and empty actual run cache; independent review; parent finalizes registration, source pins, and lease. No launch authority is included.
