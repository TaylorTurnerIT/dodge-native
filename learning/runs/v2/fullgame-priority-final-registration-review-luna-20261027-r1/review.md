# Final registration review

**Result: blocking finding. Do not start first uniform from these registration bytes.** The six index hashes match, but all six fail the worker's static preflight validator.

## P1 — Final registrations fail the priority contract

**Path:** `learning/runs/v2/fullgame-seed-priority-experiment-luna-20261027-r2/contracts.py:187`; consumer: `contracts.py:244-250` (`preflight` calls `validate_static`).

`validate_static` requires exact equality with a three-key `priority` dictionary: `uniform_floor`, `hard_component`, and `sampling_probability`. Each final registration also includes `frozen_labels`, `online_refresh`, and `stale_transition_replay`. Exact equality fails with `ValueError: priority probability or component mix differs` for all six registrations.

**Trigger:** worker CLI enters `contracts.preflight`, which calls `validate_static` before launch-approval validation or cache checks.

**Consequence:** first uniform and every paired registration stop before worker dispatch. Parent approval, launch marker, and correct lease cannot pass this source check.

**Minimal reproduction:** run `contracts.validate_static(reg,startup=False)` against any indexed final registration. Each raises the quoted error. Replacing only `reg['priority']` in memory with the exact three-key expected dict allows every remaining static check to pass; this isolates the discrepancy without changing files.

## Registration and input checks

- Parent index SHA: `7570550c86b4e7160f9e6d2ae5673c71ddf6cd41e218b5d98a1baa39790e14a9`; all six registration file hashes match their index rows.
- Requested first-uniform registration SHA matches: `993b260d191962643420c63d5c75af7298d86e5861f030a30837846e1c51ccba`.
- All six registrations match their r2 drafts after parent status, launch flag, pending fields, run ownership paths/lease, and per-run cache path are accounted for.
- Each normalized pair differs exactly by `PAIR_DIFF_FIELDS`: arm, run/claim/marker/output identifiers, and seed/component stream hashes. Per-run lease values and cache paths are distinct. Current parent state has `active_long_campaign: null`.
- All six carry matching source/runtime pins, candidate and canonical pool pins, parent registry and exclusion union, per-replica reference receipts, training-only pool role, truthful native explicit-seed evaluation metadata, 60-update PPO schedule, and requested resource caps.
- `contracts.validate_static` passes every remaining check for all six when only the priority object is replaced in memory with its expected three-key shape. No file was changed.

## Limits

This is a static registration review. It does not grant launch authority or qualify MPS, native explicit-seed behavior, accepted-checkpoint restoration, or gameplay. The parent execution index still says launch authority is false. No launch, marker creation, lease change, checkpoint load, model import, native constructor, or MPS work occurred.
