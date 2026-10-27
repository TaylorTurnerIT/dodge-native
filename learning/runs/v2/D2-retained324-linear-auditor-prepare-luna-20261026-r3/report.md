# Retained324 linear auditor successor r3

## State

The r3 OWN package is ready for parent review and later parent assembly. The r2 failure log and all r2 source, binding, and audit artifacts remain unchanged. No r3 `audit-binding.json` exists; review assembly and binding remain deferred to the parent.

The r2 full audit stopped before candidate checks because the immutable observer instantiation has no `run_id`. r3 validates its exact registration path, registration digest, observer digest, schema, and no-launch declarations. It derives run identity from the byte-pinned registration. A present but incorrect `run_id` fails. No historical record was edited.

## Source and controls

The r2 auditor package and its 24 CPU controls were copied into this OWN directory. The successor adds a test that passes the real immutable instantiation record and rejects wrong registration path/hash, observer hash, schema, launch count, marker declaration, and explicit wrong run identity. Source and numeric, array, schedule, and model parity checks remain unchanged.

The full audit remains parent-only. Bootstrap readiness stops before candidate audit and checkpoint deserialization. No candidate audit, checkpoint load, training, evaluation, MPS, environment, lease, state, marker, or receipt operation ran.

## Validation

All 25 CPU/source tests pass under the lexical project venv with `-B`, one thread per configured CPU library, `PYTHONPATH` unset, and an empty auditor-owned r3 cache prefix. The tests include positive use of the real registration and immutable observer record. The root README remains at SHA-256 `be478416b33c772a7ff9c28f2c974f767c205f7df77bcf7346ab36133d384652`.

The auditor runs as a separate process with its own r3 bytecode prefix. Parent driver must check the registered worker prefix at `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/empty-pycache` is empty before and after bootstrap/audit. Existing observation records retain both paths: the worker prefix above and the auditor's r3 prefix. Do not change worker or source import policy.

## Parent handoff

Parent creates a new reviewed assembly against `review_assembly_contract.json`, then supplies its exact digest to the binding builder. Parent freezes `audit-binding.json`, supplies its independently computed digest, and runs bootstrap readiness under the exact lease. Full audit remains parent-only after bootstrap readiness.

`output-manifest.json` does not list its own digest. This is deliberate: the manifest records every other listed output hash without a self-hash cycle.
