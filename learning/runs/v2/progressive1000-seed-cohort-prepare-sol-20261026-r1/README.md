# Progressive1000 seed/cohort proposal

Prepared only; historical freshness remains **blocked**. No registration, reservation, launch, acceptance, or training authority is granted.

- Proposed study: `progressive1000-confirmed324-20261026-r1`; three new complete six-field vectors, paired across progressive1000 and constant `3e-5` control. Both arms retain accepted324 entity transformer, reward, KL, and 60 global updates. [Exact vectors and accepted324 offsets](seed-vectors.json).
- Proposed shared D2 evaluation cohort: inclusive `0xD3000000..0xD30003FF`, 1024 ascending seeds. Six predetermined update60 endpoints plus accepted324 once: 7168 normal-start, cutoff-disabled episodes. Hexadecimal D300 does not open difficulty D3. [Exact cohort and inherited reporting contract](cohort.json).
- Current covered subset: **87,430 unique real observed seed values**, including 70,301 from original training journals; **zero proposed-cohort collisions**. Nineteen original training journals replay against the pinned Rust seed algorithm with zero mismatches. A separate conservative construction envelope contains **164,385** unique values, also with zero cohort collisions. These are seed-value counts, not independent episode counts.
- Scan opened 1937 selected JSON/JSONL inputs from a 40,972-path snapshot. Real benchmark memory/throughput logs, probes, ranking, consumed confirmation, action-mode evaluations, discarded branches, and complete discarded training updates are included where observable. Copies, fixtures, future proposals, and unresolved provenance have separate categories. [Coverage map and gaps](coverage-map.json), [path inventory](coverage-inventory.json), [per-file coverage](coverage-files.json), [pinned inputs](input-manifest.json), [prior-audit reconciliation](prior-audit-input-reconciliation.json).
- Full history is not closed: missing construction/reset-attempt receipts, unjournaled failures, excluded/ambiguous histories, and non-JSON/outside-v2 records prevent a historical known-consumed nonoverlap claim. No global-workspace freshness claim is made. Prior ten-node lineage receipt is pinned evidence, not proof of every workspace execution. [Reconstruction bounds and logged reference vectors](history-reconstruction.json).

All 192 initial slot controls use the exact accepted324 per-slot episode indices, phase324/cumulative372. Future controls cover 512 episode indices per slot per replica (98,304 arithmetic draws), not the entire future stream. No within/cross-replica repetition or new-cohort hit appears in this bounded sample. [Initial controls](initial-slot-controls.json), [future controls](future-controls.json).

One bounded future value, `97593849` (replica1, slot17, episode760, counter0), intersects only the conservative historical envelope: master `4200000000`, slot44, episode48. It is absent from the real observed set. The envelope deliberately enumerates unused zero-origin prefixes under new masters; this intersection does not establish consumption. Proposal, cohort, and vectors remain unchanged; parent must reconcile rather than silently filter or replace them.

The proposed canonical sorted, merged inclusive union is:

```text
B     0xB0000000..0xB00003E7
D128  0xD0000000..0xD000007F
D100  0xD1000000..0xD10003FF  opened ranking
D200  0xD2000000..0xD20007FF  consumed confirmation
new   0xD3000000..0xD30003FF  proposed D2 evaluation
E     0xE0000000..0xE00003E7
```

[Proposed exclusion contract](proposed-exclusions.json) and [stdlib helper](seed_controls.py) require this union in both arms before construction. Current `seed.rs` accepts arbitrary additional ranges, adds mandatory B, merges overlap/adjacency, rejects full-u32 coverage, and rehashes excluded candidates. Current `env.rs` computes seeds before `Slot::unstarted` at construction and reset. This source inspection does not prove the accepted or successor binary implements those bytes. The frozen exact-five-range validator is untouched; parent needs a reviewed successor binding the six-range union and native preconstruction/reset behavior.

Parent gates, in order:

1. Close the historical construction/attempt inventory, including discarded updates, probes, benchmarks, failed resets, and ambiguous records. Pin master/slot/episode/rejection identity and source algorithms. Retain this exact cohort if collision evidence appears; block and report it.
2. Register/reserve the three complete vectors, shared cohort, actual future stream bounds, and the effective exclusion union in both arms. Verify every initial construction and reset before native construction; log attempted and actual seed metadata, including failed startup/reset attempts. Add any further parent-reserved actual-seed exclusions explicitly and regenerate reviewed controls without silently changing vectors.
3. Independently measure fresh CPU/MPS initial reference states for all three new-study vectors before actual restore. Bind studyID, replica, all six fields, canonical vector hash, backend/version, accepted324 checkpoint/integrity/confirmation pins, fingerprint implementation, and independent provenance. Existing accepted LR-study states cannot be used. [Reference requirements](rng-reference-requirements.json).
4. Review successor source/native/collector/evaluator identity, disabled-cutoff parity, resource limits, and acceptedR5 durable restore/reseed plumbing. Freeze parent registration and exact one-shot authorization separately. Matching stream origins does not imply identical reset counts across arms.

B/E qualification, D3 difficulty, and student work remain closed. D100 and consumed D200 cannot supply fresh confirmation. Reporting remains Worst/Q1 mean/Mean/Q4 mean/Best, all milestones, and death accounting under the pinned r3 design. Later acceptance requires a separately fresh registered confirmation cohort and explicit parent policy.

Verification: 17 stdlib synthetic/arithmetic tests passed, including 76 logged historical Rust-stream reference vectors, all exclusion edges, normalization/full-union failures, both-arm missing-cohort rejection, acceptedR5 canonical hash compatibility, 192 initial controls, and bounded future collision controls. No policy/minibatch RNG was read. [Tests](test_controls.py), [test log](tests.log), [receipt](receipt.json), [output hashes](output-manifest.json).

Reproduce from workspace root (writes only this owned output):

```sh
PYTHONPYCACHEPREFIX="$PWD/learning/runs/v2/progressive1000-seed-cohort-prepare-sol-20261026-r1/empty-pycache" python3 -B learning/runs/v2/progressive1000-seed-cohort-prepare-sol-20261026-r1/prepare.py
PYTHONPYCACHEPREFIX="$PWD/learning/runs/v2/progressive1000-seed-cohort-prepare-sol-20261026-r1/empty-pycache" python3 -B learning/runs/v2/progressive1000-seed-cohort-prepare-sol-20261026-r1/test_controls.py
```

The first retained preparation log records an overbroad path-filter rejection of `progressive1000` as `E1000`; the owned filter was corrected to require token boundaries. Only preparation was rerun. No actual campaign or reference probe was attempted.
