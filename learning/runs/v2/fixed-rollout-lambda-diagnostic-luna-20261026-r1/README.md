# Fixed-rollout lambda diagnostic

Small CPU-only analyzer for a future separately captured immutable rollout. Run `python diagnostic.py` only via a caller that imports `analyze` and supplies approved arrays; CLI intentionally absent. `controls.py` runs synthetic correctness controls only.

`analyze(data)` returns JSON-safe moments; `load_npz(path)` reads plain numeric NPZ with pickle disabled; `json_text(result)` serializes with NaN rejection. See `CONTRACT.md` for schema and limits.
