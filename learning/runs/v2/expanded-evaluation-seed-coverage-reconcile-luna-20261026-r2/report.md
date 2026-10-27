# Expanded evaluation seed coverage reconciliation

Read-only JSON/JSONL metadata reconciliation. No checkpoint payloads, native runtime, or Torch imported. Proposal cohorts unchanged; no registry, reservation, lease, gate, or launch state changed.

## Finding

No collision found in prior audit logged subset. Full exclusion proof unavailable: receipts expose next indices and counters but not immutable original environment master-seed identities or a complete closed set of environment constructions for every completed, abandoned, and in-flight attempt. Candidate copy paths are not substituted for proposal exact original paths. B/E outcomes remain unopened.

## Parse-error provenance

The sole prior parse error is `learning/runs/v2/postovernight-long-D2-boundary-review-r3/inner-publication-fixture-r2/execution/inner-verification.jsonl` (SHA-256 `866c591f572083857925e197053a707013186c524f526414c4eabd4e658973ea`, 28 bytes). Its path is explicitly within `inner-publication-fixture-r2`; sibling `.inner-failure.json.pending` sits under that fixture's campaign. It is synthetic publication-fixture material, not an original training journal, so this one error is excluded from training coverage counts. The source is untouched.

## Candidate ancestry records

| Phase | Run ID | Config SHA-256 | Episode journal SHA-256 | Next-index bounds (slots) | Cumulative counters |
|---:|---|---|---|---|---|
| 180 | `D2-gradient-alignment-20261025-r2` | `2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3` | `d3cc61cd4bd7c6669e485c3fbf1d781604332f1b38fff6300091dc8ce8fefd58` | 164–208 (64) | `{"environment_decisions": 3735552, "optimizer_steps": 28384, "raw_frames": 14917917, "updates": 228}` |
| 204 | `D2-best180-branch-luna-20261026-r1` | `2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3` | `e570e3171811fd7af8f92ffc78c73727cbe790d7621bc8d197e955e912df6f03` | 183–228 (64) | `{"environment_decisions": 4128768, "optimizer_steps": 31136, "raw_frames": 16488827, "updates": 252}` |
| 276 | `D2-retained204-lr1e4-20261026-r1` | `f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628` | `cf4d146616ca236e822745f76b191e76f9dfaea6b0e1a102e22e005c665afe41` | 236–281 (64) | `{"environment_decisions": 5308416, "optimizer_steps": 40352, "raw_frames": 21202529, "updates": 324}` |
| 300 | `D2-retained276-lr3em5-20261026-r2` | `1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8` | `906aabe555df5ef3ee7b9fa6d2357dd8c564375dca21c09003082ccf57716091` | 251–296 (64) | `{"environment_decisions": 5701632, "optimizer_steps": 43424, "raw_frames": 22774103, "updates": 348}` |
| 324 | `D2-retained300-continuation-20261026-r1` | `1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8` | `de47073768b6027476683a8e1f77f0aacae438cada75fc7ea04e50ed9254bf15` | 261–311 (64) | `{"environment_decisions": 6094848, "optimizer_steps": 46496, "raw_frames": 24345721, "updates": 372}` |
| 348 | `D2-retained324-linear-lr-20261026-r1` | `missing` | `28bf332705f5e4b9c34e48f1a809ab802e69f6394e577eee2eadb133a88f93eb` | 292–339 (64) | `{"environment_decisions": 7077888, "optimizer_steps": 54176, "raw_frames": 28275027, "updates": 432}` |

Exact original candidate paths, expected candidate hashes, receipt/audit paths and hashes, receipt-parent hash links, and available seed fields are in [`reconciliation.json`](reconciliation.json). Candidate copies were not substituted for proposal paths. Receipt links close ancestry through phase 324; the phase 348 candidate is still awaiting parent finalization, per proposal.

## Why full coverage proof is unavailable

The checked accepted receipts expose per-slot next indices and counters, but not an immutable original environment master seed tied to every run and a frozen SplitMix64 implementation/source identity. Nor is there a receipt-hash-closed inventory proving exhaustive construction bounds for completed, abandoned, and in-flight attempts. Thus episode-index ranges cannot be soundly converted into the proposed environment seeds. No SplitMix64 overapproximation is claimed, no gaps are masked, and the logged-row nonintersection remains only the strongest subset proof. B/E outcomes remain unopened.

## Minimal missing artifacts

- Per original run: parent-accepted registration/config JSON binding the exact original checkpoint identity to its environment master seed and frozen SplitMix64 source hash.
- Closed construction/attempt inventory linked by receipts, covering completed, abandoned, and in-flight jobs, with each construction start/end episode-index bound and disposition.
- Phase 348 parent-finalization receipt and complete registered ancestor receipt chain.
- Evidence that each original journal row and each construction range is represented exactly once, with journal hashes reconciled to accepted receipts.

## Reproduction

From workspace root: `python3 learning/runs/v2/expanded-evaluation-seed-coverage-reconcile-luna-20261026-r2/reconcile.py`. It reads JSON/JSONL metadata and hashes only; it does not open checkpoint binaries.
