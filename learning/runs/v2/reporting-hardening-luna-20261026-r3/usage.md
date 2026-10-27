# Reporting and preflight draft

Read-only preparation utility. It checks externally pinned parent receipt and registration bytes, validates declared-field consistency, and reports metrics from two explicit frozen evaluation JSON files. It does not launch an environment, load a checkpoint, run PPO, or change training state.

## Run report

From repository root:

```sh
python="$PWD/python/.venv/bin/python"
PYTHONDONTWRITEBYTECODE=1 "$python" -B learning/runs/v2/reporting-hardening-luna-20261026-r3/reporting_preflight.py report \
  --best-reference "$PWD/learning/runs/v2/D2-gradient-alignment-20261025-r2/development-000180.json" \
  --latest "$PWD/learning/runs/v2/D2-continuation-20261025-r2/development-000252.json"
```

Both paths are required. `BEST REFERENCE` and `LATEST` are caller-supplied labels; this tool does not infer training-parent selection or quality authority. The report validates all 64 D2 seeds (`0xD0000000` through `0xD000003F`), unique indices `0..63`, index-to-seed binding, row termination/cause consistency, and aggregate counts. It reports known death causes, caps, unknown causes, and unavailable causes. Q1 is the mean of sorted rows 1–16; Q4 is the mean of sorted rows 49–64; mean uses all 64 rows. Embedded performance and mean fields are cross-checked when present. Row order does not change canonical values.

## Inspect parent authority

From repository root, pass the receipt and registration digests obtained from the parent authority source. This accepted fixture validates the inspector:

```sh
python="$PWD/python/.venv/bin/python"
PYTHONDONTWRITEBYTECODE=1 "$python" -B learning/runs/v2/reporting-hardening-luna-20261026-r3/reporting_preflight.py inspect \
  --receipt "$PWD/learning/runs/v2/d2-gradient-parent-terminal-audit-20261025-r2/parent-terminal-receipt.json" \
  --receipt-sha256 7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903 \
  --registration "$PWD/learning/runs/v2/D2-continuation180-parent-freeze-20261025-r4/registration-proposed.json" \
  --registration-sha256 0059ce1a3f2dae18a34b085b57b251c115ac53e7bc82835a6eff2164ac70e949 \
  --output "$PWD/learning/runs/v2/reporting-hardening-luna-20261026-r3/preflight-manifest.json"
```

The inspector hashes receipt and registration bytes against external pins, then checks declared fields for consistency. It validates the shape and values of declared next indices; it does not compare them with decoded checkpoint state. It does not hash checkpoint weights, independently prove resources or outer timings, or replace execution preflight. `cumulative_D2_inclusive_wall_seconds` in the externally pinned accepted receipt is the full outer-wall authority. Optional checkpoint-local timing fields are checked only when supplied. The inspector writes the manifest with exclusive creation.

## Limits

This utility does not eliminate hardcoded constants in the frozen execution runner. It is not a generic production controller and grants no future launch approval. It can reduce manual metric drift and catch authority mismatches early. PPO, runtime, rewards, seeds, and training algorithms remain unchanged. No D3/student/B/E work is included. Obtain fresh Haiku review of the frozen tool before regular use.
