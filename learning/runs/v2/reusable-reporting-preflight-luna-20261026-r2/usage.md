# Reusable reporting and preflight

Read-only preparation utility. It checks externally pinned parent authority and reports metrics from two explicit frozen evaluation JSON files. It does not launch an environment, load a checkpoint, run PPO, or change training state.

## Run report

From repository root:

```sh
python="$PWD/python/.venv/bin/python"
PYTHONDONTWRITEBYTECODE=1 "$python" -B learning/runs/v2/reusable-reporting-preflight-luna-20261026-r2/reporting_preflight.py report \
  --best-reference "$PWD/learning/runs/v2/D2-gradient-alignment-20261025-r2/development-000180.json" \
  --latest "$PWD/learning/runs/v2/D2-continuation-20261025-r2/development-000252.json"
```

Both paths are required. Labels reflect these explicit inputs; the command does not inspect training state, select seeds, or change the parent. Q1 is the mean of sorted rows 1–16; Q4 is the mean of sorted rows 49–64; mean uses all 64 rows. Death counts follow normal, kamikaze, explosion, moving, static order. The negative control reproduces phase-252 inclusive percentiles `617.25 / 2415.25`, distinct from canonical tail means `532.8125 / 3192.3125`. Shuffling rows leaves canonical values unchanged.

## Inspect parent authority

From repository root, pass the receipt and registration digests obtained from the parent authority source. This accepted fixture validates the inspector:

```sh
python="$PWD/python/.venv/bin/python"
PYTHONDONTWRITEBYTECODE=1 "$python" -B learning/runs/v2/reusable-reporting-preflight-luna-20261026-r2/reporting_preflight.py inspect \
  --receipt "$PWD/learning/runs/v2/d2-gradient-parent-terminal-audit-20261025-r2/parent-terminal-receipt.json" \
  --receipt-sha256 7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903 \
  --registration "$PWD/learning/runs/v2/D2-continuation180-parent-freeze-20261025-r4/registration-proposed.json" \
  --registration-sha256 0059ce1a3f2dae18a34b085b57b251c115ac53e7bc82835a6eff2164ac70e949 \
  --output "$PWD/learning/runs/v2/reusable-reporting-preflight-luna-20261026-r2/preflight-manifest.json"
```

The inspector verifies exact input digests, accepted D2 status, clean worker/outer exits, empty cancellation lineage, run/checkpoint/registration identity, phase and local/cumulative counters, runtime and policy pins, all 64 next indices, and cumulative plus per-iteration outer-wall accounting. It writes a new manifest with exclusive creation.

## Limits

This utility does not eliminate hardcoded constants in the frozen execution runner. It is not a generic production controller and grants no future launch approval. It can reduce manual metric drift and catch authority mismatches early. PPO, runtime, rewards, seeds, and training algorithms remain unchanged. No D3/student/B/E work is included. Obtain fresh Haiku review of the frozen tool before regular use.
