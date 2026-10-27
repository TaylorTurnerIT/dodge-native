# Review: D2 retained300 parent closeout and continuation receipt

Verdict: **no blocking findings**. Four low-severity documentation and field-semantics gaps. Review does not accept or clear authority.

## Verified against closed artifacts (static, hash and arithmetic)

- Hashes match for `audit.json` (046cc985), `completed-iteration-receipt.json` (b170f68c), `retained-best-candidate-receipt.json` (ccc73fbc), `retained-best-decision.json` (58f167f4), `full-audit.json` (048c9dcb), selected checkpoint `checkpoint-000300-candidate.pt` (e2c8fbe4), its sidecar (7d6f5eb8), `development-000300.json` (9c8ac125), `development-000300.jsonl` (2c6b2dba), parent terminal receipt (d64d0f80), and `registration.json` (8e17e118).
- Config, policy, runtime, and native hashes match `registration.json`. Parent lease `0b5cf72b` matches.
- Counter chain is consistent for updates, environment decisions, raw frames, and optimizer steps (324+24=348; 324+60=384).
- Wall chain is consistent: 4760.0624+430.1473=5190.2097; 7118.7821+1502.5563=8621.3383; 4760.0624+1502.5563=6262.6187.
- Selection: candidate 300 has the highest mean alive frames of six (2704.390625, +8.89% over 276). All caps 0, deaths 64.
- `state-after-lease-clear.json` shows the r2 lease cleared at `2026-10-26T16:30:32.621873`.

## Not verified by reviewer

- Learner fingerprints (model, optimizer, RNG). Not decoded, per scope.
- `next_episode_indices` contents (length 64 verified; not compared to parent state).
- Observer hash, process absence, identity hash.

## Findings (all low)

1. **F1, field naming.** `candidate_parent_checkpoint_sha256` is `0b5cf72b` (parent of the run). The continuation parent is `checkpoint_sha256` `e2c8fbe4`. A registration keyed on the name would load update 276 and miscount by 24 updates. Add an explicit `continuation_parent_checkpoint_sha256`.
2. **F2, stale sidecar.** `checkpoint-000300-candidate.pt.json` still says `provisional_pending_parent_terminal_receipt` / `training_eligible: false`. Preflight must gate on the candidate receipt plus the parent terminal receipt. Fails closed if misread.
3. **F3, lineage gap.** The run's phase-276 checkpoint (`165ae5c5`) differs from parent `0b5cf72b`. `entry-restoration.json` shows model, Adam, and RNG matched the parent. Same eval mean (2483.65625), so no selection change. Receipts never name `165ae5c5`.
4. **F4, budget base.** Future baseline 5190.21 includes a 19.685 s highwater offset (4760.06 vs parent point 4740.38). Conservative and registered. No field states which clock (5190.21, 8621.34, or 1502.56) the next budget charges. Add `continuation_budget_base_seconds`.

Full detail: `review.json`. Input and output hashes: `receipt.json`.
