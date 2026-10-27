# r3 preparation findings

- Fixed terminal candidate counter lookup: entry checkpoint 204 has zero local counters; checkpoints 216–276 bind to their real update-journal rows. Focused production-helper test checks all seven candidate updates and rejects out-of-range updates.
- Entry evaluation now compares all 64 phase-204 rows with the selected parent immediately after evaluation and before rollout. Production-validator test accepts exact rows and rejects a mutated row.
- Worker exception path sets `status="failed"`, including finalization failures. Final checkpoint digest now reads the explicit phase-276 certificate.
- LR helper verified loading, immutable pre-override optimizer digests, saved-copy LR assertion, seven embedded candidate/model/checkpoint/counter/resume/identity/evaluation gates, caps, run ID, seed, and arm config bytes remain preserved from r2.
- Haiku r1 F1/F2 fixes were parent-tested in r2. F3 archival values are externally labeled. F4/F5 addressed above. F6/F8 comments and digest source corrected where relevant. F7 atomic publication was not changed; existing failure receipt and nonzero exit remain acceptance barriers.
- CPU-only focused tests and exact registration pin preflight passed. Full `validate_outputs` was not run because no real campaign output exists. Parent must run full frozen gate for any actual retained output.
