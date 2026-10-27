# D2 retained324 linear runner registration contract

Registration builder must bind this frozen runner to the independently assembled companion adapter and schema. It must write exact SHA-256 values into `pins`; runner, local schedule, adapter, schema, and launcher are critical pinned inputs. Do not copy mutable companion files into this directory.

## Identity and source pins

- `run_id`: `D2-retained324-linear-lr-20261026-r1`
- `run_seed`: `4200000001`; no reserve seed or retry.
- Parent: selected checkpoint SHA-256 `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`; selected receipt SHA-256 `76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08`.
- Inherited counters must be complete and contain `updates=372` before schedule initialization.
- Critical source pins: `runner.py`, `lr_schedule.py`, companion `parent_adapter.py`, companion `registration_schema.py`, and the frozen `execute_once.py` at `D2-retained324-continuation-prepare-luna-20261026-r2`. Bind their exact bytes; do not fill adapter/schema hashes from historical source values.
- `runner_path`, `lr_schedule_path`, `parent_adapter_path`, and `registration_schema_path` must resolve inside this r3 directory. The runner independently checks the helper path and digest before import. Launcher path and digest must match the frozen source.

## Schedule metadata

Use `lr_schedule.py` specification digest `SCHEDULE_SPEC_SHA256` and the runner's registered local helper digest. Checkpoint identity carries `lr_schedule` specification and `lr_schedule_spec_sha256`. Checkpoint state carries `lr_schedule` with origin 372, horizon 60, completed count, specification digest, and optimizer parameter-group count.

At original parent restore, restore model, Adam, and RNG in frozen order; confirm exact equality; require complete inherited counters with `updates=372`; then initialize schedule metadata. Entry checkpoint at cumulative 372 must save completed count 0 and optimizer LR `3e-5`. Saved checkpoints at cumulative 384 and 432 must validate LR against schedule state. A future scheduled resume must reject absent schedule metadata and any disagreement between saved completion count and actual cumulative updates.

Stage the next LR from `372 + local_updates` after rollout and before PPO. Keep staged schedule and progress separate. Commit schedule metadata and runner counters only after PPO output, finite metrics, update-progress, gradient diagnostics, explained-variance agreement, and effective optimizer LR checks pass. A failed PPO or diagnostic may leave optimizer/model state partially changed; stop and report failure. Do not claim optimizer rollback.

Training metrics must record cumulative update, schedule progress, and LR for every optimizer parameter group. Preserve existing checkpoint/evaluation, environment, PPO, guards, receipts, and journal behavior.

## Cost and provenance

- Keep selected trajectory baseline `5678.9823631240915` seconds.
- Keep selected checkpoint's original producing-cost receipt as lineage only: original campaign cost baseline `9758.365427209174` seconds and historical original300 terminal receipt SHA-256 `7c6f250b5c5aa9e4098603cc8772c532a713e65f478cbda6ebfdd3941692fc9b`.
- Bind the latest completed-cost receipt separately: `D2-retained324-parent-terminal-audit-20261026-r1/completed-iteration-receipt.json`, SHA-256 `d3ddc427f18c8a88c45439452c9efcd966daefe423222e0fa03e97ff4f4fc7d3`, latest campaign resource cost `10824.835578584221` seconds.
- Do not replace selected-checkpoint ancestry or trajectory time with latest campaign cost. Companion adapter/schema must represent both authorities separately.

The builder supplies final registration SHA-256 and companion adapter/schema source digests after those files are final. This contract intentionally does not invent them.
