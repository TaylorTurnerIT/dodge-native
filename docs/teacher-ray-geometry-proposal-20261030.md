# Teacher clearance rays, 2026-10-30

**Design and source audit; source-only prototype added after Taylor's “Go”.** Start with eight static, player-clearance rays as a cheap alternative to a same-input grid/CNN. Taylor's hypothesis is that explicit wall/escape geometry could reduce pattern deaths. This is plausible, not measured. Rays remain Priority 14, after the focused credit-horizon/configuration work; no campaign execution is authorized.

Scope: geometric inputs only. The other idea thread owns observable heuristic **outputs as inputs**. No action scores, masks, heuristic recommendations or oracle labels enter this proposal. Parent worktree `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79` remains read-only; DODGE-051's exact lease and `learning/runs/v2/k1-horizon-screen-20261030-r2` are outside scope. Preserve the failed DODGE-050 r1 AC-power episode and all partial evidence.

## Evidence and information boundary

Audited local source at `4a18b173987ab8e735cdadb70fe3538377d2a8bf`: [features](../crates/dodge-rl-env/src/features.rs), [literal geometry](../crates/dodge-rl-env/src/geometry.rs), [raster](../crates/dodge-rl-env/src/raster.rs), [player/collision physics](../crates/dodge-core/src/game.rs), [teacher](../python/dodge_rl/models/teacher.py). Apply the [Goal/clairvoyance rule, P7 and Priority order](review-ideas-and-scaling-plan-20261030.md).

Local venv and notebook SQLite are absent. Read `research_log.py` context by restoring tracked `learning/research/records.json` into **in-memory SQLite**, using its existing `Store.restore/context` methods and stdlib Python. No notebook files changed. Retrieved DODGE-039/047/048 and DODGE-050/051: rays remain unobserved; grid costs are analytical; the snapshot's DODGE-051 status predates the running state supplied in this task. No live parent campaign status was inspected or inferred.

Every branch receives exactly `global_feats [B,1,14]`, `entity_feats [B,80,16]`, `entity_types [B,80]`, `entity_mask [B,80]`. Sanitize masked rows/types **before** any decoding, reduction or lookup. No auxiliary tensor, diagnostics, serials, full lists, offscreen hidden geometry, pattern/seed IDs, timers, RNG, hidden history-valid flags, simulator future or engine-oracle supervision. Actor and critic retain the same information boundary. Admitted partly offscreen boxes keep their literal coordinates.

Source facts affecting interpretation:

- `features.rs:454–475` already supplies player position, velocity, size and four normalized wall gaps. Rays add an inductive bias and directional combinations, not new wall information.
- `game.rs:9–12,1286–1303` clamps the **player center** to `[2,125]` on each axis, independent of size. Symmetry axis is **63.5**, despite feature centering at 64. Friction is exactly `52_428/65_536`, followed by acceleration `0.5` per pressed axis. Clamping position does **not** zero velocity. A wall is a movement limit, not a lethal obstacle.
- `features.rs:357–402` paints all admitted enemy geometry before its 64-token cap; warning-segment positions also enter the auxiliary raster but not the four arrays. Do not feed that raster into this comparison. Rectangles have 16 slots; excess admitted rectangles raise an error, rather than silently truncate. A 64-enemy observation cannot reveal whether anything was dropped.

## Static ray contract R0

Use ordered unit directions E, SE, S, SW, W, NW, N, NE; screen y increases downward. Diagonals have components `±1/sqrt(2)`. Eight directions match the movement axes and diagonals; neutral is not a ray. Distances are **Euclidean pixels of player-center translation**, not action duration or guaranteed reachable travel.

Decode `p=(64+64*g[0],64+64*g[1])`, size `s=4*g[4]`, entity center `c=(64+128*e[0],64+128*e[1])`, signed half-extents `h=64*e[2:4]`; endpoints are `l=c-h`, `u=c+h`. Never sort endpoints, take absolute extents, clip boxes to the arena or re-create hidden native coordinates. Float32 decoding is authoritative for this derived representation; it cannot promise Q16.16 boundary identity.

For direction `d`, define three distances:

1. **W:** first center-clamp boundary: minimum nonnegative `(125-p_a)/d_a` for positive components or `(2-p_a)/d_a` for negative components. Ignore zero components. Do not subtract player size again.
2. **L:** first strict collision with a represented **currently lethal** type 1–3 or 7–8 row (`e[15]=1`), within W. Exclude beneficial types 4–6.
3. **B:** first collision-shaped boundary of any represented rectangle, ignoring its current lethality, within W. B is a current rectangle-body cue; it is not a prediction that a benign/fading rectangle will become lethal.

For each hazard family, use the correct player endpoints (`geometry.rs:155–179`): enemy-family player box `[p-(s-1),p+(s-1)]`; rectangle player box `[p-(s-2),p+(s-2)]`. The powerup box `[p-s,p+s]` concerns pickups, not lethal clearance. Native enemy bounds are `[x,x+size]`; native rectangle bounds are `[x,x+width-1]`, likewise y. These endpoints are already encoded by c/h; do not subtract one twice.

Compute collision by intersecting the **literal strict inequalities** on each axis:

`l_a - r < p_a + t*d_a < u_a + r`, with `t >= 0` and `t <= W`.

Return the infimum of the nonempty strict-collision set. Current strict overlap gives distance zero. Mere touching is not current overlap; touching followed by entry may also have distance zero. A tangent with no strict interior is a miss. A zero-direction axis must satisfy strict overlap throughout. A point hazard can collide with a wide player. An inverted hazard may also collide if player width makes the translated strict interval nonempty; otherwise it is a miss. Do not drop inverted rows before testing. This differs deliberately from raster coverage rules.

**Fixed 46 scalars:** eight each of W, L, B, hit-L and hit-B (40), then current strict-overlap-L, strict-overlap-B, represented enemy count/64, rectangle count/16, enemy-count-equals-64 and any represented inverted hazard (6). Distances divide by `H=123*sqrt(2)`; a missing L/B uses distance H plus hit=0. Hit masks distinguish miss from a hit at H. W is always known under the admitted player contract. Combined clearance `min(W,L)` is derivable; keep wall versus hazard distances separate so the policy can learn their different meanings.

**Confidence semantics:** L/B are exact only for the decoded, represented static scene under this contract. A miss means “no represented collision along this segment,” never certified free space. Enemy saturation is a caution cue, not an overflow-validity flag; lack of saturation does not certify unseen warnings or future spawns. No fabricated confidence probability. Strict overlap and inverted flags derive solely from the arrays.

## Motion, mechanism and limits

R0 uses no extrapolation or new history. Existing `e[6:10]*4` contains measured center/half-extent changes per **raw frame**, not per K-step; `g[2:4]*2.5` is player velocity. First/unknown history also produces zeros. Zero cannot distinguish stationary from unmeasured motion; `until_lethal=1` likewise conflates several phase cases. No metadata may disambiguate either.

A later **separate R-motion arm** could append the first-hit entity's radial closing estimate `(v_player-v_entity) dot d`, plus its measured extent-change cues, using exposed deltas only. This is a local rate estimate, not a trajectory, time-to-death, exact moving-slab solution or engine future. Do not add it to R0. Any additional history must declare its raw-frame cadence/window, causal association rule and reset behavior, and be available identically to every arm and the student; current row indices are not stable enemy identities. Pixel-stack recoverability still needs review.

Hypothesis: near-wall motion can leave only one escape corridor while a rectangle closes it. W/L/B make the short direction and current rectangle enclosure easy to read, potentially reducing late reversals in patterns 3/39. The cited review reports turns and suggests cul-de-sacs; its detailed checkpoint-420 telemetry directory is absent here, so those associations were not re-audited. No pattern identity becomes an input or supervision label.

Failure alternatives: walls already suffice in global features; discount horizon, exploration or action sampling causes the deaths; eight spokes miss narrow oblique gaps and hazards between spokes; nearest-hit reduction loses topology and hides blockers behind the first; B over-discourages safe crossings; inertia makes geometric openings unreachable; unknown motion/phase and truncated warnings defeat the cue. Rays offer neither path connectivity nor a viability guarantee. Lower action switching alone could mean paralysis. The wall-zeroes-velocity explanation is specifically unsupported by source.

## Rays versus grid/CNN and patch tokens

All costs below are source arithmetic, not measured latency, memory qualification or efficacy. Preserve the 81-token legacy transformer. Add `latent + gate * branch` after its final normalization and before both original heads; initialize only the gate to zero, branch weights nonzero. Isolate constructor RNG. Require unchanged initial logits **and values**. Do not append zero tokens to legacy self-attention: that changes its softmax denominator.

| Representation | Added parameters / core MAC ratio | Tradeoff |
| --- | ---: | --- |
| R0: 46→64→128 MLP, GELU, one scalar gate | 11,329 / about 1.00045× | At most 640 entity-direction tests/state, shared across L/B reductions; continuous subcell clearance, limited topology |
| C: same-array 8×16×16 grid, P7 CNN and 2×2 pooling | 62,977 / 1.1692× | Coarse layout and interactions; 8-pixel cells erase narrow gaps |
| P: same grid, 64 patch tokens, separate gated cross-attention | 171,522 / 1.6835× | More spatial detail/attention cost; defer until C earns its cost |

Baseline has 321,290 parameters. R0 adds 11,136 linear MACs versus baseline core 24,592,896. R0 float32 storage is 184 bytes/state versus grid 8,192: 2.875 MiB versus 128 MiB at 64×256 states, or 92 MiB versus 4 GiB at 512×1,024. Derive features per minibatch instead of persisting rollout duplicates. CPU reductions, transfers, backward and allocator overhead remain unmeasured; theoretical cheapness does not qualify 6 GiB RSS/MPS use.

Reuse [P7's cost/proxy scope](../learning/runs/v2/spatial-teacher-proposal-parent-20261030-r7/spatial-cost-scope.json), rebuilding its grid exclusively from the same sanitized arrays. Positive grid intervals use half-open coverage; points paint their containing cell; inverted intervals paint nothing. Rays must retain literal inverted collision semantics. That loss is a representational limitation of C/P, not permission to repair geometry or import missing data. P7's estimated 12-frame phase channel remains an observed estimate, not a native future label.

## Required source-only checks before any runtime request

Future implementation approval should cover pure derivation and reviewable synthetic tests first:

- Four-array-only function boundary; masked NaN/Inf/type sentinels cannot change outputs. Reject invalid **valid** rows through the common input validator. Permuting represented rows leaves rays unchanged; static reductions need no identity/tie history.
- Fixtures at all clamp faces/corners, cardinal/diagonal distances, exact touch versus entry/tangency/overlap, size 2 point rectangle-player, size 4 player, signed/point/inverted boxes, partly offscreen boxes, beneficial entities and all-masked scenes. Test the literal inequality oracle written from this contract, not merely helper-to-helper equality.
- Hold arrays fixed while varying forbidden metadata, warning-only geometry and overflow-dropped entities: R/C/P unchanged. Same sanitized array hashes and allowed causal history in every arm, including critic/label path. No auxiliary-target shortcut. Test saturation without claiming actual overflow.
- Exact zero-gate legacy latent/logit/value parity, isolated RNG, serialization round trip, gate gradient opens with nonzero branch. Later PPO needs reviewed name-based Adam mapping; never positional copying or edits to an old capsule.
- Reflection/rotation fixtures use axis 63.5, correct ray/action permutation and vector signs. Check derived-feature equivariance; do not claim full-game D4 symmetry. Adversarial float-boundary fixtures document discrepancies rather than forcing native parity.

## Bounded future comparison; predictions before execution

Propose **E/R0/C**, two independent fit seeds per arm, six warm-start fits from the same frozen checkpoint420. This is a proposed alternative to P7's E/C/P proxy, **not** an amendment or extra active reservation. The only intervention per arm is representation branch; hold labels, state bank, minibatch order/exposure, optimizer, endpoint rule and controller fixed. Pair fit-seed identities across arms. No action-output features, shields, motion variant, reward/horizon/schedule changes or D4 augmentation. Capacity confounding remains; a later matched latent-MLP control is required before attributing a gain specifically to rays/spatial bias.

Use P7's observable-expert gate and fixed seed-grouped 384/64/64 split: 512 already-consumed training-pool seeds, two behavior episodes each, at most 32,768 states. The original FullState heuristic and engine oracle remain ineligible labelers. Two fit seeds are optimizer replicas, not two game seeds. Fresh Adam 1e-4, eps 1e-5, batch512, clip0.5, hard observable-expert-action CE, frozen critic head, no PPO/value/auxiliary loss; cap each fit at 20 epochs or 2,000 steps, first reached. Critic values can still drift through the encoder. Terminal and validation-selected endpoints remain distinct; test/survival never selects the endpoint.

Proposed ceilings reuse P7: expert qualification 17m; bank/labels 1h3m; six fits 2h12m; clean follow-up 4h12m; standing noise follow-up 4h12m. **Total 11h56m**, no extra ray arm added on top of P7. Approved byte-identical shared bank/expert receipts may remove duplicate work only through parent reconciliation. Forecast full path plus 20% margin and I/O within each cap before approval. Separate 6 GiB RSS/MPS guards, exact-once execution, no automatic retry/replacement/extension; qualifying prefixes count inside budgets. No concurrency with the active parent campaign.

Follow-up count: six fixed fit endpoints +420 +observable expert, each on 1,024 already-consumed telemetry seeds at K1 and K4 = **16,384 new clean games**. Four noise conditions on a fixed 256-seed subset = **16,384 additional games**. No cache substituted for newly counted matched clean controls. This is exposed development evidence, not fresh-cohort confirmation or proof of better PPO learning. No cohort is allocated here; promotion would require a separately approved fresh ≥1,024-seed confirmation and training-replica evidence.

For each K separately, primary endpoint is Q1 (mean worst-quarter alive frames), plus Worst/Mean/Q4/Best, milestones and early deaths. Epsilon0.01/0.05 uniformly replaces a decision among nine actions, including the original; log realized changes. One/four-raw-frame causal FIFO delays start neutral, hold last applied action until due and clear at reset. Require qualified raw-frame execution. Keep policy/executor RNG separate from native RNG; delay-zero/no-noise must preserve clean control. Noise doses per game-second differ with K. Apply perturbations after any selected request; never re-mask noise.

Report paired noise-minus-clean contrasts with 2,000 shared-game-seed bootstrap draws; sort each condition independently for marginal Q1/Q4. Show both fit replicas separately: game-seed bootstrap is not training-seed uncertainty. Track intended policy, selected and executed action switches separately, excluding resets/initialization, retaining prior action across rollout boundaries; report within-episode denominator and switches/1,000 raw frames. Without a shield, intended and selected should match. Retain P6 entropy/soft-target diagnostics; reduced jitter is not distillation quality.

**Predictions, before any future execution:** R0 should fit the observable labels faster/cheaper than C and improve E's clean Q1 if directional clearance is the missing bias; C may win where connectivity/layout matters. A useful signal is positive R0-minus-E Q1 in both fit replicas, paired uncertainty reported, with Mean and noisy tails inspected for regression—not automatic acceptance. Lower CE without survival improvement supports only imitation fit. Zero Q1 gain despite better near-wall geometry weakens this mechanism; switching reduction with more early deaths supports over-avoidance/paralysis. Noise gains are diagnostics, not a posthoc selection rule. Performance, resource results and causal mechanism remain **unobserved**.

Taylor's subsequent “Go” approves source-only R0 derivation, gated adapter and synthetic/equal-input tests. It does not approve campaign model restore, fitting, games, native/MPS work, seed opening, notebook reconciliation, lease changes or promotion. Parent owns later notebook IDs and any execution registration.

## Source-only implementation after “Go”

Implemented the [stdlib R0 reference](../python/dodge_rl/clearance_rays.py) and [opt-in CPU adapter](../python/dodge_rl/models/ray_teacher.py); neither is wired into campaign runners. Extracted legacy `encode` without changing parameter names or arithmetic, avoiding duplicate head execution. The reference uses decoded Python scalars and is not a vectorized or resource-qualified training frontend. GPU/MPS input is rejected.

The [guarded source-test runner](../python/tests/run_ray_source_checks.py) blocks native imports, restricts global seeding to CPU and trips on accelerator RNG/memory APIs. It tests scratch CPU weights, including an in-memory synthetic serialization round trip, never a campaign checkpoint. Tests cover a rational literal-collision oracle, float32 boundary neighbors, clamp/point/inverted geometry, masking/permutation, counts, D4 geometry, gate gradients, and exact logits/value/latent/attention parity against the pinned prechange teacher source. [Check receipt](teacher-ray-geometry-source-checks-20261030.json) retains outcomes and environment.

Independent review remains pending under the task's “Do not spawn agents” instruction; these are self-checked synthetic results. Survival, pattern-death improvement, student recoverability, preprocessing/transfer cost and resource qualification remain unobserved. Any runtime request still needs independent review and separate parent approval; no notebook, parent runtime, weights, cache, marker, lease or ledger was changed.
