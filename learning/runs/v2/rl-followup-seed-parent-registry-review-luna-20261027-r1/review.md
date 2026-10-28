# Seed pool and future cohort reservation review

**Result:** No blocking findings plus limits.

- Registry, accepted pool, and whole-document canonical pool hashes match their recorded pins: `544037dd8e452d01660438fefbfed6990f34ce81572ccf678a539d9dc73c8172`, `5093727c2fdabd794267ccbc44a43b1fb29747b545cff645b66b0ad578180f04`, and `5ed500167f97f17092fe8ca0fd581d3342366dde09f68f1fd8130db56e4f522f`.
- All four registry artifact pins and the candidate manifest pin match. All 41 pool verified-input rows match immutable manifest metadata and on-disk size/digest. The ledger reference resolves to the immutable snapshot. The initial mismatch was path representation only: relative pool path versus absolute manifest path; role and digest match.
- Recomputed 5,605 candidate median labels and SHA-ranked selection. The accepted pool exactly matches the top 256 per stratum (256 `alive_ge_1000`, 256 `hard_alive_lt_1000`); labels and selection keys match. All selected evidence is marked training-only. No evaluation seeds contributed to selection.
- Pool seeds do not overlap the registry exclusion union. D4 reserves 1,024 seeds and D5 reserves 2,048 seeds in their listed disjoint ranges. Registry disables launch authority and online priority updates.
- Source scope is accepted formal CONTROL worker-result snapshots. Selection labels are noisy median-survival strata, not oracle failure classes.

**Limits:** History closure is bounded to the recorded accepted324 lineage and related recorded runs. It makes no universal workspace nonuse claim. 122 historical file roles remain unresolved; qualification content isolation did not pass. This review does not resolve those limits or qualify source/registration/runtime behavior. It does not authorize a launch.
