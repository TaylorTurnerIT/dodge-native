# Lower learning-rate resume arm: preparation

Status: hook frozen after CPU tests. No environment, rollout, optimizer step on accepted game weights, campaign, lease, or registration created.

## Transition

The arm changes only PPO learning rate from `0.0003` to `0.0001`. Keep Adam `eps=1e-5`, betas, clipping, PPO, entropy, reward, K=4, attention, model, optimizer moments, counters, and RNG from the exact accepted parent. Apply the hook only after model/Adam/RNG restore and the existing exact-parent equality check, before environment construction or first update. Reassert effective LR at restore and before each update.

Hook mutates only `optimizer.param_groups[*].lr`. It rejects any requested rate other than exact `0.0001`, any group not restored at exact `0.0003`, and empty groups before mutation. It returns the declared field delta. Do not call `load_state_dict` after the hook; that restores parent LR. Negative-control test proves detection.

## Evidence and identity

Parent checkpoint: `105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea`. Accepted parent receipt: `7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903`. The retained-best policy names update 180 as incumbent; recheck it after the unchanged control and reconciliation. Do not infer a future arm parent from an old ranking if policy has changed.

Keep parent checkpoint, sidecar, accepted receipt, and their hashes immutable. New arm receives its own config SHA, source/runtime identity, run id, registration, and receipt. Parent provenance must separately bind parent config SHA and the accepted parent identity. Existing strict config/identity checks stay strict; add a narrow, declared transition validator that permits only the LR field and arm identity delta. Recompute the source and registration pin manifests for the new capsule. Existing adapter pins `CONFIG_SHA`, run identity, and runtime and cannot run this arm from a config-only change.

The optimizer fingerprint changes at exactly the group LR. Compare full Adam state after removing only `param_groups[*].lr`; retain and report both full fingerprints and the exact LR delta. Do not label the full optimizer fingerprint unchanged.

## CPU validation and bounds

Unit tests use a synthetic loaded Adam state with nonempty moments and the actual accepted checkpoint. The actual checkpoint is hash-validated and loaded on CPU; exact model and Adam state are loaded without environment, gradients, or optimizer steps. Its stored sampling RNG backend is MPS, so the frozen full restore API rejects CPU RNG restoration by design. The CPU hook test therefore verifies its own CPU RNG remains unchanged. Existing frozen evidence separately reports accepted complete model/Adam/MPS-RNG restore on MPS; this task does not repeat MPS work.

Proposed future arm limit: 1,800 seconds total wall, 6 GiB RSS and 6 GiB MPS driver caps measured separately. The ranked plan estimates 1,165 seconds training plus evaluation; prior continuation observed 1,165 seconds (72 updates), 1,921,928,192-byte RSS, and 2,447,998,976-byte MPS driver peak. Preflight against current run policy and cutoff; keep cleanup inside the total wall cap. Request no more than 1,800 seconds. Budget is a cap, not a raw-frame target.

Use 72 updates and same 64 D development seeds, same order, deterministic argmax, paired against current unchanged C0. Match the registered training seed for first arm pair, but create fresh independent registration only after control result/reconciliation. Because one seed per arm cannot resolve effects below roughly 620 frames, require a second registered C0 and LR-arm pair with a new shared run seed before reading a small positive result. Compare paired dev mean alive frames; report Q1/Q4, score, approx-KL, clip fraction, completed epochs, early-stop, entropy, and seed-level bootstrap interval. Replace retained best only after exact candidate and eval audit, and only on strictly higher dev mean. No qualification claim.

## Next registration steps

1. Finish the active unchanged-best180 control and reconcile its result against current policy.
2. If update 180 remains incumbent, prepare fresh registered arm source/runtime/config with exact parent and receipt pins, narrow LR transition, unchanged protocol/seed exclusions, and no reused lease.
3. Register a separate unchanged C0 seed-2 control and the matched A/C0 seed-2 pair only under explicit parent authorization. Do not auto-launch, acquire a lease, or start training from this preparation.
4. Independent review the hook, adapter patch, transition validator, budget/cutoff preflight, and pin manifests before any campaign registration.
