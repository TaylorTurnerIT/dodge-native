# Remaining seed-priority r3 bindings (prospective, no launch authority)

Study `fullgame-seed-priority-luna-20261027-r1`. The uniform replica-1 run is done and parent-audited
(registration `015464219f...`). This packet binds the five other arms to the reviewed r3 source
(source `a29e25b2...`, runtime `e032a5ab...`, accepted checkpoint324 `c10d90ec...`): replica-1 priority and
replica-2/3 uniform+priority. Original run IDs, six-key RNG vectors, audited CPU/MPS references and
pool/provenance are preserved. Budgets, LR 3e-5, 64x256x60, cap18000, normal starts, limits and the
frozen 512 pool are copied unchanged. Nothing was launched, claimed, leased or loaded.

## Contents
- `<run_id>/registration-final-candidate.json`: exact registration bytes, run-private paths, fresh lease token, empty `empty-pycache/`. Each is the reviewed r3 draft passed through the same transform that reproduces the first run's final registration byte-for-byte.
- `registration-index-proposal.json`, `parent-gates-proposal.json`: prospective, `launch_authority:false`. Pins exclude the broken r2 manifests, the consumed first authorization, the first launcher, and the mutable ledger (`state.json`). Only the immutable ledger snapshot is pinned.
- `start_remaining_one.py`: one-run launcher. Refuses without a promoted index, approved gates and a pinned parent authorization naming that exact run and registration SHA. Materializes `registration-final.json` as a byte copy of the candidate only after all checks pass. Refuses the already-run replica-1 uniform.
- `watch_progress.py`: read-only bounded monitor. `launch-blockers.json`: exact blockers. `build_remaining_bindings.py` and `build-receipt.json`: builder and its record. `run_tests.py`, `tests/`, `logs/test-summary.json`: 33 stdlib CPU/fake checks.

## Candidate registration SHA-256
See `registration-index-proposal.json` (`runs[].registration_sha256`).

## Promotion and launch (parent, only after review and a fresh user message)
1. Parent writes `fresh-user-authorization.json` (schema `fullgame_seed_priority_remaining_user_authorization_v1`; `runs` = exact `{run_id, registration_sha256}` pairs, `retries: 0`).
2. Parent writes `parent-gates.json` = proposal with `status: approved_exactly_once_per_registered_run`, plus `authorization_path`, `authorization_sha256`, `proposal_sha256`, and the authorization file added to `pins`. Parent writes `registration-index.json` = proposal with `status: reviewed_exact_registrations_parent_promoted`.
3. For one run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<run>/empty-pycache <interpreter> -B start_remaining_one.py --run-id <id> --index-sha256 <sha> --gates-sha256 <sha>`. Audit each run with r3 `audit.py` after the launcher's `execution-exit.json`, as for the first run.

Candidates carry `launch_authority:true` and `status:parent_registered` only because the r3 contract requires that form of a registration; that is not user authorization.
