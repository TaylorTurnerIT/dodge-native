# R1 lifecycle review addendum

### P1 — Terminal checkpoint validator reads manifest hashes from wrong identity level

- Producer: `successor_identity.py:12-13` nests `runtime_manifest_sha256` and `source_manifest_sha256` under `identity.successor_runtime`; `runtime_adapter.py:236-240` stores that object as sidecar `identity`.
- Consumer: `terminal.py:121-130` compares both fields directly on the top-level `identity`.
- Trigger: Any successful worker reaches global update 60 and terminal audit validates its checkpoint sidecar.
- Consequence: The producer's valid nested identity has no top-level manifest hash fields, so `terminal.validate_outputs` rejects the completed run with `global60 checkpoint identity/update/parent boundary differs`.

R2 corrects this consumer shape; this addendum applies only to frozen r1. No package input changed.
