# Native/collector integration review

No blocking findings within the original finite CPU unit integration scope. Parent alone accepts; this review grants no runtime/training qualification or launch authority.

Reviewed `../progressive1000-native-collector-integration-sol-20261026-r1/` using source reads, hashes, AST and saved JSON. No target imports, tests, native execution, Torch/NumPy, model/environment construction, build, checkpoint, MPS, repair, subdelegation, commit or push.

## Evidence

- **Identity/parity:** `common.py:39-48`, `run_units.py:38-43,64-95`, `parity_driver.py:14-68`. Old/new paths, file identities and hashes differ. Separate isolated processes load one explicit extension each; no harness path reuses an earlier target module. Complete result/reset digests cover dtype, shape, C-order bytes, scalar hex and all metadata. Four complete old/new cases match; all eight rolling chains recompute across 2,048 saved entries. Each binary records 58 deaths/resets, zero caps and no cutoff calls.
- **Collector/oracles:** `integration_driver.py:39-63,91-127,160-184,198-268`; `successor/ppo.py:306-379`; `tests/test_collector.py:35-45`. Policy/value inputs are observation tensors only. Native reconciliation precedes audit/storage; final observations precede reset. Scalar GAE recurrence, death-zero bootstrap, alive-final-value bootstrap, reward-leak perturbation and owned-storage checks are meaningful. Saved counters/rewards, combined reset order, episode increments and assignment identities independently agree: seven H1000 cutoffs at decision249; one death at frame631/decision157; 8,191 gameplay frames, eight accepted resets, two subset calls and 104 reset startup frames.
- **Failure/split:** `integration_driver.py:270-301,319-328`; `successor/curriculum.py:322-367`. The post-reset guard failure retains slot1 episode1 as `unassigned_unaudited`, null generation/horizon/ordinal, 13 returned startup frames and no new assignment. Full256 and split128+128 saved batch hashes, step records and snapshots agree. Completed updates remain0, pending update1, scheduler generation0.
- **Hashes/repair/resources:** All 47 artifact entries, all 20 Python sources, all 64 protected pins, 12 initial copied-source hashes and 17 invocation source hashes match. Collector/tests are byte-identical to accepted R2. `finish_units.py:45-101` and `repairs/control-import-r1.diff:1-20` preserve the first failure and change only owned harness root/import path/result name. Logs/receipts agree on eight API and 41 inherited fake controls. Five initial children plus one fake-only repair record absent groups; aggregate29.116314875194803s, maximum15.989594625076279s, each below120s and aggregate below300s. Passing native cases were not rerun.

Detailed checks: [hashes](hash-checks.json), [parity](parity-checks.json), [integration records](integration-checks.json), [execution receipts](execution-checks.json). All target files and 64 inputs still matched at review exit.

## Pins

- `integration_source_manifest_sha256`: `a4ce9ef84e92482ba6b658446bc2aede8fb1814f545a4719e42af7db13fc4a69`
- `integration_artifact_manifest_sha256`: `f58d070e0e1dddd720301779ae8f39ecbe134835047c6763e7108be0e4d879a7`
- `integration_receipt_sha256`: `3f3427a8f56a324cc1749902b661b7b838ff3128fe77e5e5371040c347ea2925`
- `inputs_sha256`: `677593532ab91e93f01fc80746685a7e220ddf6233df8781ce57fcd0e8d19d5d`
- `new_native_sha256`: `29d49a1317ebe1367932e88514f744242a8e67cf7e6d7d0ab64d5f008cbed567`
- `old_native_sha256`: `022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e`
- `collector_source_manifest_sha256`: `16200c082f53f62eb01c068de18ebd826da8d3a06969ce82de1c218c70f9d8f9`
- `design_sha256`: `c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0`

## Limits

Actual collector coverage is D1 only. H2000/ordinary18000 cap, exact-H death, simultaneous death/cutoff and decision255 boundary were not reached. Prior Rust/fake coverage remains inherited. Split buffers cover one pending update, not two successful updates. Historical exclusions establish a floor, not complete freshness.

Original arrays/tensors were not regenerated. GAE, bootstrap/storage and process-group absence remain source-reviewed author execution evidence. Initial metadata JSON loses tuple/list types; rolling checks start from recorded initial digests. The frozen baseline `ppo.py` has only the disclosed post-run hash (`receipt.json:98-105`).

Finite comparisons do not establish global source/binary correspondence. Full runtime/evaluator identity, real restore/RNG references, fresh cohorts, resource calibration, registration and leases/markers remain separate parent gates. Writes stayed in this review directory; no whole-workspace concurrent-write attribution.

Machine-readable result: [receipt.json](receipt.json).
