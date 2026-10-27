# Retained324 linear registration successor

Own output: `D2-retained324-linear-registration-luna-20261026-r1`. This directory implements the parent adapter, strict registration schema, and deterministic registration builder for scheduled treatment `D2-retained324-linear-lr-20261026-r1`.

No final registration is present. Builder waits for immutable runner, schedule-helper, and launcher manifests. Runner must reside in `D2-retained324-linear-runner-luna-20261026-r3`; its `lr_schedule.py` must match accepted helper bytes `35fee3a73fc1b283c5412d577ccee8635caa26f6fbf251e10009566c3a18fbc6`. The launcher must be a reviewed `execute_once.py` in this own-output directory, with explicit immutable runner-module binding. Builder only writes registration with exclusive creation after all source and receipt checks pass.

## Parent authority and cost lineage

- Selected state remains original checkpoint `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`, authorized by original selected receipt `76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08`.
- Checkpoint producing-run lineage remains pinned to completed-cost receipt `7c6f250b5c5aa9e4098603cc8772c532a713e65f478cbda6ebfdd3941692fc9b`. Its before cost is `8621.338345875141`; selected checkpoint cost uses this original baseline plus its current-iteration wall.
- Latest cost receipt `d3ddc427f18c8a88c45439452c9efcd966daefe423222e0fa03e97ff4f4fc7d3` is a distinct accounting-only authority. Its before cost equals original producing receipt after cost `9758.365427209174`; its after cost is `10824.835578584221`, adding `1066.4701513750479` outer seconds. It adds no learner ancestry. Adapter rejects an invented `competence_passed` key.
- Original checkpoint trajectory remains `5678.9823631240915`. Do not substitute discarded endpoint384 or reserialized checkpoint `bffa...`.

## Schedule contract

Use cumulative updates 373 through 432, 60 updates total, with linear LR `3e-5` to `1e-5` inclusive. Origin is 372, horizon is 60, and LR applies after rollout before PPO update. Registration binds spec SHA `7ceed85c5dc277602f2f51937b4ac003e2013e2689341a963ce5d82d5b64c9e4`, accepted helper SHA above, and a per-optimizer-group per-update LR log. Keep evaluation updates 324, 336, 348, 360, 372, 384. Keep limits 1750 planning, 1790 work, 1800 total, 10 cleanup, and 6 GiB each RSS/MPS. Preserve other PPO settings.

Run ID is `D2-retained324-linear-lr-20261026-r1`; master seed `4200000001` remains paired with completed fixed control. Builder checks output path collision but does not reserve or consume a seed, inspect lease/state, launch, or create a marker. Expected lease remains declarative.

## Launcher assessment

Frozen `execute_once.py` imports `runner` and `registration_schema` by bare module name from its own source directory. It cannot be reused byte-identically with an external r3 runner. Builder therefore requires a separate reviewed launcher manifest and explicit path binding. This directory does not yet include that launcher, so builder cannot emit final registration.

## Verification

`tests.log` records 12 CPU-only checks. Tests use immutable JSON receipts and synthetic state dictionaries; they do not load checkpoint tensors. They cover selected authority, source digest drift, receipt status, both cost-chain edges, fabricated authority, strict IDs/schedule pins, and deferred assembly with synthetic immutable runner/helper/launcher fixtures. No launch, preflight, lease/state read, seed reservation, checkpoint binary read, MPS, or training occurred.
