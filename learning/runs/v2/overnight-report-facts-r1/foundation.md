# Stable foundation evidence for the overnight report

This is report preparation, not the final cutoff report. D2 was still active when the parent state was read. No project code, tests, Torch, native environment, training, or evaluation ran for this collection. Exact input hashes are in `facts.json` and `inspected-inputs.json`.

## Implemented work

M0 supplies the isolated original-engine baseline/profiling harness. M1 adds deterministic headless stepping, on-demand post-method rendering, and borrowed privileged geometry while preserving the legacy cached-pixel boundary. M2 adds the core-only Rust/PyO3 vector environment with fresh seeded episodes, K=4 reward aggregation, typed AABB/slab features, observed motion history, visibility/warning rules, owned arrays, masks/pixels, explicit episode boundaries, Rayon chunks, and GIL release. M3 adds the specified full teacher, PPO, curriculum/evaluation runner, identity and immutable checkpoint handling, resource supervision, and terminal-success authorization.

## Baselines

All D2/D3 baselines use 1,000 paired original-engine episodes per policy, patterns/powerups on, K=4, and an 18,000-frame cap. D2 random/neutral/heuristic mean score is 0.353/0.340/100.1075; mean alive frames is 255.323/187.861/6,114.593. D3 means are score 0.338/1.884/88.633 and alive frames 198.354/152.966/4,030.038. Heuristic caps are 15/1,000 at D2 and 2/1,000 at D3. These observations are censored. Full median/p90 tables remain in the two baseline result documents and `facts.json`.

Observed maxima across baseline configurations were 18 enemy-family records and 16 rectangles. Defaults remain 64/16 with overflow guards; this is not a universal capacity proof.

## Engine and environment evidence

M1-r2 passed 72 workspace tests, including 15 headless fixtures, formatting, and workspace/all-target/all-feature Clippy with warnings denied. Its 100×2,000 comparison includes 200,000 frames, of which 171,650 are dead residence; separate targeted fixtures and all 39 catalog entries cover active mechanics. Legacy capture fingerprints and new post-method render boundaries have distinct tests. External Pemsa runtime validation was not run.

The M1 short matched benchmark measured full 54,774.23 raw frames/s, headless 14,521,044.81, and headless/render-K4 427,142.51: ratios 265.107× and 7.798×. It used 64 short death-stopped episodes, 16,142 frames per round, five rounds. M1-r2 reused the identical-runtime r1 measurement and did not rerun it. Later core metadata source changed; these ratios are not current final-core/PPO claims. The later metadata benchmark observed time changes of +0.79% headless, +1.15% render-K4, and +1.55% full, with overlapping noise and no causal overhead conclusion.

Accepted M2-r2 parity covers 2,000 paired episodes and 10,146,614 raw frames per path, including all 39 patterns at D2 and D3. Python trajectory checks cover normal and ragged termination, two thread/chunk configurations, pixels/auxiliary targets, array ownership, and resets. The rendered B8 memory workload retained 101 RSS samples across 100,000 measured calls after 5,000 warmup calls; median growth was 3,014,656 bytes, below the fixed 64MiB threshold. This establishes an empirical plateau, not zero leaks.

M2 public B32 step/reset measurements were 8,281.09 and 9,412.90 calls/s headless at 1/1 and 4/8 threads/chunk; rendered rates were 1,548.50 and 3,481.72. They include features/returned arrays and limited bookkeeping, exclude construction/warmup, and do not measure PPO. M2 core metadata separately reran 86 workspace tests. The binding-stage receipt reports 41 unit plus 35 primitive Rust tests, 68 Python tests, formatting and workspace/all-target/all-feature Clippy; it explicitly did not run whole-workspace tests. Do not add these milestone counts together or call old tests new validation.

## Neural foundation and safeguards

The teacher has 321,290 parameters, 81 tokens, width 128, two full self-attention layers, four heads, 14 global features and 80×16 entity features. Final changed-runtime integration passed 312 Python tests on 75 pinned inputs. Both frozen r3 Codex reviews returned no findings. Free OpenCode could not provide a verdict because quota was exhausted; that limitation remains explicit.

Five runtime findings were repaired: cancellation orphaning; interrupted-update resume eligibility; checkpoint-local wall-budget reset; swallowed nonfinite probe errors; and transition eligibility surviving failed/cancelled parent runs. Same-phase resume is disabled pending safe cumulative budget anchoring. Registered transitions require successful exact terminal evidence and a parent-pinned lease anchor; a candidate certificate alone is insufficient.

The final report must retain provenance caveats: overwritten intermediate extension binaries were not independently archived; one M2 original-control source label needs its explicit executed-source pin; and one initial failing M3 test fixture was hash-recorded but not fully archived. Final/negative-control test versions and corrected production evidence were audited. Saved source receipts, static review, live runtime, learning, and final teacher qualification remain separate evidence classes.

## Work still outside this collection

The parent must add actual D2 terminal outcome and audit status. D3 cannot start after 12:20 UTC under the unchanged full 1,800-second stage plus 600-second reserve rule. Final B qualification and E replication remain unopened. The teacher must beat the measured D2/D3 heuristic on the immutable score-and-survival gate before any student work. Visual palette embeddings, 8px patches, staged DAgger/auxiliary losses, and future distillation remain deferred.
