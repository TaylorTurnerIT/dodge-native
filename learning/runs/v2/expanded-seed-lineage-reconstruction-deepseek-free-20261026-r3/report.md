# Seed lineage reconstruction (348 checkpoint)

Scope: accepted checkpoint `b95228e5…` (`D2-retained324-linear-lr-20261026-r1/checkpoint-000348-candidate.pt`). Its ancestry is a linear 10-node chain: D1 pilot → D1 curriculum-9 → D2 v3-72 → D2 continuation-132 → 180 → 204 → 276 → 300 → 324 → 348. Every node's checkpoint SHA-256 matches the expected hash and the parent links; every registration or parent-lineage link names the prior checkpoint path and SHA. The chain is rooted at the pilot, whose identity has no parent.

Seed source: `crates/dodge-rl-env/src/seed.rs` (`239cb9d8…`), stream `dodge_slot_splitmix64_high32_reject_v1`, exclusions B/D128/E. Native bindings are D1 `967c7249…` and D2 `022d41dd…`. All 19 top-level journals replay: 158,524 seed records, 13 run seeds, 0 unmatched. Inherited `abandoned_*` blocks replay against the parent run seed.

Bounds enumerate every slot/episode below each producing run's final resume index. Ancestor closure: 120,829 draws, 105,874 unique seeds. The 19-journal envelope: 163,556 draws, 163,553 unique. All 862 journal paths (858 regular plus 4 symlink aliases) contain 70,301 distinct actual seeds.

Collisions: 0 in ranking `0xD1000000..0xD10003FF`; 0 in confirmation `0xD2000000..0xD20007FF` and its 1024 prefix. No reseed or filtering was applied.

Boundary: this proves ancestor training exposure, not global workspace nonuse. D3 seed `5562881586070242563` has no journal; six top-level directories lack journals; 843 nested journals were seed-scanned but not replayed; B/E outcomes remain unopened. The r3 revision proposal labels the r2 manifest path but records the r4 2048-seed SHA; the range is unaffected. Checkpoint bytes were hashed only; no payload deserialization. No frozen input was modified.
