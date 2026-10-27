# D2 retained300 registration evidence map: static checklist

Scope: static reads and sha256 only. No runtime, tests, decoding, MPS, environment, training, ledger/lease/sharedsource writes. No launch qualification. Not a throughput proof.

## Pins (full sha256)

- [x] Selected receipt `retained-best-candidate-receipt.json`: `ccc73fbc72c83e9dc061ad11be536b2e0d7cb076319e6d7cff27b9f2a0f8838d` (rehashed)
- [x] Producing-run completed receipt `completed-iteration-receipt.json`: `b170f68ce68c98e1a0d7511fed71f978732731895446214966da1402caea863a` (rehashed)
- [x] Full audit `full-audit.json`: `048c9dcb2d001e6b93f45224e4a6636ab660b6b6777f6d380a1acc69301de28b` (rehashed)
- [x] Parent audit `audit.json`: `046cc985ce2ac42cc1ba3d7988da3787c7758df8fe849b7ceb5b9a30f631586b` (rehashed)
- [x] Selection decision `retained-best-decision.json`: `58f167f4e93d4e7e9b50dd587db273255c65c56ffb6d7f30ac7bcd938e368fdf` (rehashed)
- [x] Producing-run registration `registration.json`: `8e17e1188253f091b62a8b60397663a530c4a865166f9568978dd009148308e7` (rehashed)
- [x] Producing-run worker result: `9345be58fe7fa7becb2de39b6064927255ba20398298f4cd4a44a4fdb27e9cdd` (rehashed)
- [x] Execution result: `bb42f88669a0b458d0e13a630361dd8c3b011692919d5c31ef722c99960b816f` (rehashed)
- [x] Integration contract: `b36dea935e44d5de928ab7749e9d64b015577d6dfacb7134f1e5bfdd929e33e5` (rehashed)
- [ ] eval300 JSON `development-000300.json`: pin `9c8ac12576e4582ab6b2a30a82a56a595c904dc6bc31543f021c59517cd73046` (receipt value; file not rehashed)
- [ ] eval300 JSONL `development-000300.jsonl`: pin `2c6b2dba46b4fc3b4961bfbadec687923b39c7aa97550fd99cbf34a9a439b5b0` (receipt value; file not rehashed)
- [ ] Sidecar `checkpoint-000300-candidate.pt.json`: pin `7d6f5eb8bca5758bbf7bf71a6615eabca823f48703b6d22798587cafced9f8ac` (receipt value; file not rehashed)
- [ ] Checkpoint `checkpoint-000300-candidate.pt`: `e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710` (pin only; not decoded, not rehashed)

## Selected-300 predicates (static)

- [ ] Selected receipt `checkpoint_sha256` == `e2c8fbe4...` and `candidate_phase_update` == 300.
- [ ] `candidate_local_update` == 24; `candidate_cumulative_counters.updates` == 348.
- [ ] `completed_iteration_local_updates` == 60; `completed_iteration_phase_update_end` == 336 (endpoint336 not selected).
- [ ] `candidate_parent_checkpoint_sha256` == `0b5cf72b...` (original producing-run ancestor, kept separate from new parent `e2c8fbe4`).
- [ ] `parent_registration_sha256` == `68063348...` (ancestor) and `registration_sha256` == `8e17e118...` (producing run). Do not swap.
- [ ] `competence_passed` == false; `training_continuation_eligible` == false and `stage_promotion_eligible` == false on completed receipt (no stage authority).
- [ ] Decision `endpoint336_not_selected` == true; `selection` == `retained_best_integrity_accepted_checkpoint`.
- [ ] Full audit `mode` == `full_parent_only`; parent audit `status` == `accepted_completed_iteration_and_selected_intermediate300`.
- [ ] Counter sets: selected300 local24 / cumulative348; producing run completed336 / local60 / cumulative384 (worker-result). Expected new total 408 = 348 + 60.

## Endpoint276 to intermediate300 validator changes

- [ ] Replace stale selected-trajectory literal `4760.062404125177` (276 `runner.py:27`) with `5190.209660791156`.
- [ ] Replace stale parent literals in `runner.py:31-34` (4740.377…, 1388.330…, 4755.588…, 5533.299…) with selected300 values where the gate is about the selected point clock. Keep worker-result field names.
- [ ] `runner.py:222-223` ancestry values (3352.046…, 4129.756…) are not the new chain; replace with selected300 values.
- [ ] Total-resource baseline for the new run: `8621.338345875141`. Keep it separate from the selected-trajectory baseline.
- [ ] Pins to add to final input set: producing-run full audit `048c9dcb…`, parent audit `046cc985…`, upstream parent terminal receipt `d64d0f803d02a8d2c33da9fa0ba862f06ba7d9c56dcf4f0494e559a49e48fcc4`, registration `8e17e118…`.
- [ ] Limits unchanged from 276: work 1790, outer 1800, cleanup 10, RSS/MPS 6442450944.

## Parent narrow worker clock values (selected300 receipt)

| Field | Value (seconds) | Source |
|---|---|---|
| future checkpoint trajectory baseline | 5190.209660791156 | selected receipt `wall_accounting` |
| selected checkpoint reported cumulative D2 wall | 5190.209660791156 | selected receipt `wall_accounting` |
| selected checkpoint reported trajectory wall | 5190.209660791156 | selected receipt `wall_accounting` |
| selected checkpoint current-iteration wall | 430.1472566659795 | selected receipt `wall_accounting` |
| completed campaign cost before (producing run) | 7118.78208862512 | completed receipt |
| completed campaign cost after (total resource) | 8621.338345875141 | completed receipt / decision |
| completed discarded branch highwater | 6262.618661375197 | completed receipt |
| observed outer, producing run | 1502.5562572500203 | completed receipt / parent audit / full audit |

Note: worker-result `current_iteration_observed_outer_seconds` is 1498.3960853749886 (worker-internal). Observer outer is 1502.556. Difference 4.160 s. Use observer outer for budget accounting.

## Work budget arithmetic

- [x] `1502.5562572500203 * 1.15` = 1727.9396958375232. Not 1750.
- [x] Gap 1750 - 1727.94 = 22.06 s. 1750 is conservative (higher) but is not derived from this formula. Parent should state it as a chosen margin.
- [x] work 1790 + cleanup 10 = outer 1800.

## Seed 4200000000

- [x] Scanned all JSON under `learning/runs/v2` under 20MB (2385 files with run_seed/seed text).
- [x] No recorded `run_seed` value equals 4200000000 except the integration contract.
- [x] String hits in `registration-proposal.json`, `preparation-receipt.json` (r4), and `function-stats.json` are not run_seed records.
- [ ] JSONL/log string hits not classified.
- Static scan only. Not a reservation or guarantee.

## Known gaps

- [ ] R5 runner/launcher components not read (excluded).
- [ ] Nested full-audit fields not mapped beyond top-level keys.
- [ ] Checkpoints, eval JSON/JSONL, and sidecar not rehashed.
