# Review: D2 retained300 parent adapter (R3, read-only)

Scope: `learning/runs/v2/D2-retained300-parent-adapter-luna-20261026-r3/` (unchanged R3). Static reads and SHA-256 only. No imports, decoding, tests, MPS, training, or state/lease edits. R4 not read.

Verdict: no blocking defects. The validator's pins, literals, flags, and clock arithmetic match the real selected receipt, the completed-cost receipt, and the sidecar. This review makes no launch qualification claim.

## Verified against bytes (static)

- All pinned inputs match their recorded hashes (see `receipt.json`): checkpoint `e2c8fbe4`, selected receipt `ccc73fbc`, completed cost receipt `b170f68c`, sidecar `7d6f5eb8`, and the R3 outputs.
- Selected receipt: schema, status, `training_continuation_eligible=true`, `stage_promotion_eligible=false`, `competence_passed=false`, `checkpoint_metadata_unchanged=true`, `candidate_phase_update=300`, `candidate_local_update=24`, `config_sha256=1c24df3e`, and `candidate_parent_checkpoint_sha256=0b5cf72b` all match `parent_adapter.py` lines 6–15 and 28–44, 66–68.
- Future trajectory baseline `5190.209660791156` matches in the receipt and the cost anchor (adapter lines 72–74, 104).
- Completed cost receipt: schema, status, before `7118.78208862512`, after `8621.338345875141`, 336/60/384 counters, and both ineligibility flags match adapter lines 97–114.
- Sidecar equals the `checkpoint_metadata` dict literal the adapter expects (lines 38–42).
- Module shadowing: no `parent_adapter` or `json`/`torch` module found on the test's `sys.path` entries. The `RUNTIME` and `PREP` directories contain no conflicting module.
- `cpu-tests.log` hash `2596b2d0` matches the pin. The log shows 5 tests, `OK`. Not rerun.

## Findings

Under immutable byte pins, several checks are duplicate validation. They cannot fail unless a pin changes. They are defense in depth, not defects: receipt schema/status/flags (lines 28–34, 97–114), sidecar equality (38–42), and the metadata gate (59–62). The checks that do real cross-artifact work are the state-vs-receipt pairs (45–56), counter and lineage checks (57–70), fingerprints (84–89), LR/epsilon (91–92), and the campaign-clock arithmetic (79–83).

1. **low, coverage gap.** `test_parent_adapter.py:98–103` has no mutation for `candidate_phase_update` or `candidate_local_update` on the receipt. The validator does reject them (line 43–44), so this is missing coverage, not a defect.
2. **low, dead loop.** `test_parent_adapter.py:152–155` iterates over two SHAs and `continue`s on the real one, so only `"0"*64` runs. Behavior is correct. The loop is misleading and should be a single assertion.
3. **low, dead parameter.** `parent_adapter.py:96` declares `fingerprint=None` on `validate_cost_anchor` and never uses it.
4. **low, authority gap (prior F2 partial).** `validate_parent` does not reference the parent terminal receipt `d64d0f80` or `audit.json` `046cc985`. Authority rests on the pinned selected receipt's flags. Byte pins make this safe for these exact files. It is still a gap if any consumer treats the adapter as the full lineage check.

## Reconciliation with previous review (`D2-retained300-parent-receipt-review-haiku-20261026-r1/review.md`)

- **F1 (field naming): mitigated in adapter.** The adapter treats `candidate_parent_checkpoint_sha256` as parent-of-run (lines 66–68) and rejects a state whose parent equals the continuation checkpoint (69–70). The continuation identity is the pinned `CHECKPOINT_SHA` (line 7). Registration code outside this adapter remains exposed to the name trap. Not in R3 scope.
- **F2 (stale sidecar): partly mitigated.** The adapter requires the sidecar to stay ineligible (lines 38–42, 59–62) and does not use it as the eligibility gate. Eligibility comes from the receipt flag (line 30). The parent terminal receipt gate the review asked for is absent (finding 4).
- **F3 (lineage gap): verified.** `checkpoint-000276-candidate.pt` hashes to `165ae5c5`, which differs from `0b5cf72b`, as the prior review stated. The adapter's lineage check uses `0b5cf72b` and never references `165ae5c5`. Adequate for the adapter. The receipts still do not name `165ae5c5`.
- **F4 (budget base): open at runner level, not an adapter defect.** The adapter pins three clocks: trajectory 5190.21 (lines 72–74), completed cost 8621.34 (lines 101–102), and state campaign clock `7118.78 + 430.15 = 7548.93` (lines 79–83). It does not name which one a new deadline charges. A `continuation_budget_base_seconds` field remains a recommended addition.

## Evidence limits

- `checkpoint-000300-candidate.pt` was not decoded. Learner fingerprints, `next_episode_indices` against state, `parent_completed_campaign_cost_baseline_seconds`, and the `cumulative_successful_...` value at the selected point are all unverified.
- Tests were not rerun. The CPU log is accepted by hash only; the log lacks command, interpreter, exit code, and timestamp.
- MPS RNG was not examined.
- R4 integration was not read.
- No launch qualification claim is made.
