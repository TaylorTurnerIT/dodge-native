# Confirmation proof wiring preparation

OWN OUTPUT ONLY. Sources copied from `expanded-runner-final-parent-20261026-r6`; `selection.py` copied at the reviewed SHA `d35614e5f3d65836f0b3943622701322297bc201a0d07a2e547f5bd2a2b64e66`.

Confirmation registration uses optional `provenance.ranking_proof` with exact proof keys and six `{path, sha256}` result bindings. Worker replays the full proof through `selection.py` loaded only from a path/hash pin. Worker and validator hashes are checked around import and validation. Supervisor preflight and postflight load worker from the externally pinned registration source path. Winner 348 fails before marker claim through preflight selection validation.

Scope is preparation only. No actual outcomes, checkpoints, runtime, leases, markers, native modules, training, ranking, or confirmation were read or used. No timing qualification is claimed. Throughput compatibility remains pending parent review. Synthetic test updates for proof producer-to-confirmation end-to-end and tamper matrix remain incomplete.
