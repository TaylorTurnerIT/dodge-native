# Long D2 integrity policy redesign: independent Opus round r1

Status: proposal only, not implemented. The parent must reconcile it and a fresh review must follow. This round is read-only. It ran no imports of ML or native code, decoded no checkpoint, ran no stress or probe, and edited no state, source, protocol or lease.

## 0. Context discovered at read time

`learning/runs/v2-orchestration/state.json` (SHA256 `682f98f8…68ae`, read once as a contextual snapshot) shows the following:

- An earlier attempt at this Opus round hit `Claude API rate limit reached`.
- A Codex integrity design was registered: `postovernight-long-D2-integrity-policy-design-codex-r1/plan.json`, SHA256 `5ef2e5af…435e`.
- The parent accepted that design **for implementation only**: `postovernight-long-D2-boundary-policy-parent-reconciliation-r1.json`, SHA256 `95977b36…be9d`.
- An implementation task is running in `postovernight-long-D2-boundary-prepare-r1`. I did not read that directory's mutable contents.

This document is therefore an independent second opinion for the parent to reconcile. It does not block that work. It reaches the same core policy by a different argument, and it adds a few concrete points that would change the implementation or the tests. These are listed in §7.

## 1. What the five-second watchdog actually proved

The mechanism in the current rejected candidate (`guard-prepare-r1/long_d2.py` `Guard.full_check`/`start`) works like this:

- A background thread re-hashes all 10091 pins (about 290 MB). That includes the recursive historical R4/R3 unions, the readonly capsule walk, the legacy `check_frozen` rebuild and `check_module_origins`. A new pass becomes due 2 s after the previous one starts.
- The guard requires `end_current − start_previous ≤ 5 s`, and the resource monitor requires `now − last_full ≤ 5 s`.
- Every `guard.check(force=True)` also performs a full pass on the main thread. In the training loop that happens 3 times per update: the block loop, the `update_once` entry and the `update_once` exit.

**What it proved.** At sampled instants never more than 5 s apart, from the view of this one process, every pinned path had the expected bytes. So a *persistent* on-disk change to any pinned file would be detected within about 5 s.

**What it did not prove:**

1. **Which code executed.** Python source is read once, at import. A change to an already-imported `.py` file has no effect on the running process. Hashing that file every 5 s says nothing new about execution; it only says the file on disk still matches. A native `.so`/dylib is mapped once at load. Replacing it by rename does not affect the loaded image. On macOS an in-place overwrite of a signed, mapped image tends to kill the process rather than silently change it.
2. **Transient change and revert** within a window shorter than the sampling gap. The window was up to 5 s, and longer during native calls that held the GIL.
3. **Lazy imports or data reads** between samples. Bytes read in a window and then reverted are invisible.
4. **Malicious same-user writers.** Such a writer can also edit the verifier, the receipts or the state file.
5. **Loaded bytecode** when `__pycache__` holds stale `.pyc` files. The hash is of the source, not the cache.
6. **Archival-file integrity in any useful sense.** Most of the 10091 pins are historical evidence (old preparation, review, stress and test fixtures) that the live run never reads. A change to them mid-run cannot affect the experiment. The only thing that matters is whether the archive bytes bound in the final receipt are the registered ones, which a postflight pass establishes completely.
7. **Reproducibility.** A latency deadline is an availability property of the verifier, not a reproducibility property of training. Reproducibility comes from binding the inputs that were *consumed* (code at load, config, seeds, D1 parent bytes, runtime) and the outputs that were produced.

The 5 s rule was an orchestration choice. Nothing in `SPEC_PRIVILEGED_VIT_RL.md` or `implementation-plan-v2.md` requires it; the plan asks for "freeze source snapshots … before long experiments" and full source identity. Its practical effect was to turn ordinary OS or GIL scheduling noise into run failures: r1 stopped at a 5.005 s gap after 51 updates, and the stress test failed at a 5.459 s gap. It did not make the trained weights any more trustworthy. Wall time minus thread CPU (3.43 s − 0.45 s) shows waiting, but it does not separate GIL contention from IO or OS scheduling. I make no causal claim beyond "the verifier was descheduled".

## 2. The guarantee actually needed

The setting is a local, controlled, single-user Mac. Other agent threads can write to the same checkout, and that is the only realistic threat. For each class of event:

| Event | Is it a real risk? | Control needed | Old 5 s policy | Proposed |
|---|---|---|---|---|
| Accidental concurrent edit by another agent or tool, persistent | **Yes, the main risk** | Prevent it where cheap; otherwise detect it before the bytes are *consumed*, and always before accepting results | Detected within about 5 s | Ownership reservation; full preflight; fresh hash at consumption and at declared boundaries; postflight. Detection latency is bounded by the boundary interval (§4) |
| Accidental edit then revert (transient) | Low | Not detectable by any polling scheme | Windows of up to 5 s or more were missed | Windows are larger. Disclosed. Mitigated by hash-at-consumption for config and data and by the module-delta check |
| Malicious same-user process | Out of scope | OS isolation or a separate user | Not prevented | Not prevented. Disclosed |
| Loaded code differs from disk (stale `.pyc`) | Real but avoidable | Empty registered `PYTHONPYCACHEPREFIX`, `-B`, `PYTHONDONTWRITEBYTECODE=1` | Not covered | Covered by launch policy and a boundary assertion |
| Lazy import mid-run | Real (Torch and NumPy lazily import submodules) | Bind the origins of new modules | Indirect, and only for project modules | `sys.modules` key-set delta at every boundary: new project modules must be expected and are hashed; new third-party native origins must be in the R manifest |
| Dynamic data read mid-run (config, checkpoints, seeds) | Config and D1 are read only at startup; the run's own checkpoints are outputs | Hash the consumed bytes | Polling | Hash-bracket the consumption call (§4 B-consume); outputs hashed on write |
| Archival receipt drift | Matters only for evidence | Exact verification at preflight and postflight | Every 5 s (wasted) | Pre and post only; every path and hash kept |
| Mutable parent state | Only the lease and cancel fields matter | ≤ 0.5 s lease check | Same | Same, unchanged |
| Output tamper after write | Matters for acceptance | Hash on write; final inventory after owned writers are confirmed gone | Same | Same |

## 3. Recommended policy

**Name:** `consumption_bound_boundary_integrity`. It is essentially the same as Codex's `declared_boundary_verification_with_full_preflight_and_postflight`.

1. **Prevention by ownership, recorded honestly.** The parent reserves the original checkout's source, runtime, inputs and cache for the run. It records active T3 threads and worktrees at launch as an attestation (not OS enforcement), and does not launch writers into that checkout until the receipt is final. If the parent cannot hold that reservation, it does not launch this policy.
2. **Full B/R/A preflight in the outer process before spawn.** Every one of the 10091 old pin paths is classified exactly once (B > R > A precedence) with its original SHA, and actual directory membership is checked. Any conflict rejects.
3. **Startup consumption binding in the worker:**
   - The empty cache-prefix policy is asserted.
   - Imports run.
   - **Immediately after imports**, a fresh B pass runs, together with the real unchanged `check_frozen` and `check_module_origins`, plus a `sys.modules` snapshot of names and origins.
   - This post-import pass is the one that binds *what was loaded*. Persistent edits between preflight and import are caught here.
   - D1 restoration through the unchanged `validate_transition` is bracketed by fresh hashes of the D1 checkpoint and terminal-receipt files immediately before and after.
4. **Declared boundary checks with no time trigger.** Each check is a fresh B pass plus `check_frozen`, origins and the module delta. It runs at the existing forced boundaries, under the measured coalescing rule in §4. Non-forced `check()` never hashes.
5. **The resource, lease, cancel and wall monitor stays exactly independent.** It keeps its 0.05 s wait, 0.15 s trigger and 0.5 s gap. It never hashes, never takes the verify lock, and loses its `now − last_full ≤ 5` clause.
6. **Full B/R/A postflight in the outer process** after the worker exits and owned writers are confirmed gone, and before any `accepted:true`. If postflight fails or is missing, success is rejected and partial results are retained as ineligible.
7. **No** periodic integrity thread, fourth verifier process, import hook (`sys.meta_path`), mtime cache, cross-boundary hash cache or independent integrity IO deadline. Integrity IO counts against the same absolute role and normal or failure deadlines as all other work.

## 4. Boundary placement: a measured, pre-registered choice

The rejected candidate runs a full pass at **3 forced checks per update**. r1 averaged about 20.9 s per update across 1066.756 s and 51 updates, but that figure included the old background verifier and evaluations, so it is only a coarse reference. The cost of a B-only pass with `check_frozen` is **unmeasured**. The first pass took 0.4315 s, but it covered the full set, was probably cache-warm, and is not production evidence.

I therefore recommend that the protocol register one of two levels **before launch**, chosen by the startup rehearsal measurement and never changed mid-run:

- **Level F (full, the default):** the full boundary check at every existing forced boundary. This is the simplest option and needs no learner change.
- **Level C (coalesced):** the full boundary check at update start (the `run_schedule` loop check), at every checkpoint write (before and after), at evaluation entry and exit, at startup and at the final worker check. The other forced calls do only `sample` plus the module delta (no file hashing). This is still at least one full check per update.

Rule: let `t95` be the 95th-percentile wall time of N ≥ 5 consecutive B-boundary passes on the worker main thread in the startup rehearsal.

- If `3 × t95 ≤ 0.02 × 20.9 s` (that is, `t95 ≤ 0.139 s`), register **F**.
- Otherwise register **C**.

In both cases, record per-boundary wall and thread-CPU time and the number of files and bytes; this is required telemetry. Its loss is recorded as a diagnostic loss and never blocks the failure receipt.

This rule is an engineering cost cap, not a security claim. The guarantee difference between F and C is the detection latency for a persistent edit to a B file. Under C it is at most one update. Under both levels, all lazily consumed bytes are covered by the module delta and by consumption hashing at the next boundary, so neither level changes what is known about *executed* code beyond the transient window disclosed in §2.

## 5. Legacy paths and `check_frozen`

Keep the original package and native paths, and keep the unchanged historical validators **for this run**. `check_frozen` rebuilds against `ORIGINAL_ROOT`, and `validate_transition` binds the exact original origin and runtime. Relocating them would require a new identity and new mappings, and it risks a weakened comparison.

- Do not monkeypatch, filter or strip anything.
- The readonly capsule remains the controller and evidence store. The new protocol states explicitly that imported legacy code executes from the original root, not from the capsule.
- Copied-capsule execution under a new identity is a worthwhile **future** prevention upgrade. Its benefit is OS-level read-only execution, which is genuine accidental-write prevention. It is not needed to get a sound measured D2 baseline now.

## 6. Failure, cancellation and reporting

These rules are minimal; no event framework is needed.

- Keep **separate** fields `first_alarm` and `first_cancel`. A direct-signal descriptor contains `{signum, observed_at_monotonic, basis: handler|pending_scan, sender: "unknown"}`. A pending scan is an observation, not the kernel receipt time.
- Compact first-failure descriptor: `{role, kind, outcome, at_monotonic, timing_basis, local_seq}`.
  - A generic exception's time is when it was **first caught or observed**, never when the `Stop` object was constructed.
- Keep the local first failure for audit. The global primary is the earliest across ACKs. If a strictly earlier peer event learned later via ACK arrives, it replaces the primary. Later events never overwrite an earlier primary.
  - Ties: fixed order by kind (cancel < alarm < resource < lease < integrity < exception), then role, then `local_seq`. No physical ordering is claimed below clock resolution.
- Cleanup deadline: `until = min(prev_until, global_first.at + 10, T0 + 7210)`. It only tightens and is never reset. A late-learned earlier ACK may exhaust the cleanup allowance immediately, and that is correct.
- Signals observed after the global first failure, which the role itself forwarded (forwarding is logged before the signal is sent), are cleanup-phase observations and secondary. A direct signal that is first globally is the cancellation primary, with the sender unknown.
- Fix the reporting bug where `defer cancel@1` combined with `guard@2` reported the guard as primary.
- Telemetry IO errors are recorded as diagnostic loss. The mandatory failure receipt is attempted independently and first. Raw outer exit and wall time stay the authority.

## 7. Where I differ from or add to the accepted Codex design

1. **Post-import binding as the primary claim about executed code.** It deserves its own named boundary and receipt field (`post_import_verdict`). Today it is implicit in "startup".
2. **D1 consumption bracket.** Hash the D1 checkpoint and terminal receipt immediately before and after the unchanged `validate_transition` call, not only at the generic boundary.
3. **A `sys.modules` key-set delta at every boundary,** including those that do not hash under level C. This is cheap and covers lazy imports with no hook. New non-project native origins must be members of the R manifest.
4. **A measured F/C rule registered before launch,** instead of assuming B-at-every-forced-boundary is free. Codex says the cost is unmeasured but sets no decision rule.
5. **Explicit tie-break order** and the corrected `defer cancel@1/guard@2` regression.
6. A stronger statement that **no weakness about executed code is introduced** for already-imported modules. The removed claim concerns detection latency for unconsumed files only, plus larger transient windows. It is not "equally strong": what is lost is a fixed ≤ 5 s detection bound for persistent edits, and that bound never covered transient edits or execution.

## 8. Validation plan

The plan is frozen before execution, run sequentially, stops at the first unexpected failure, and allows no retries. Total ≤ 900 s.

- **Stdlib units and negative controls (≤ 300 s), using a toy package and fixtures:**
  - preflight corruption of B, R and A files and of membership (an added or removed file) rejects before spawn;
  - a persistent B edit after the post-import pass is detected at the next declared boundary and no later, with the boundary index asserted;
  - an edit to an A file mid-run is not detected mid-run but is detected at postflight, and success is rejected;
  - an archive-manifest SHA mismatch, or a member mismatch under a correct manifest, rejects;
  - a lazy import of an unexpected module fails at the next boundary; an expected one passes and is hashed;
  - a stale `.pyc` / cache-prefix violation is rejected;
  - a missing or failed postflight gives `accepted:false` with partial results retained as ineligible;
  - `first_cancel` and `first_alarm` stay separate; `defer cancel@1/guard@2` gives a cancel primary;
  - an earlier peer ACK arriving late replaces the primary and tightens the deadline without resetting it;
  - a telemetry write failure still publishes the failure receipt;
  - non-forced `check()` performs zero file opens (verified by counting opens with an instrumented `open` in the unit test only).
- **Real-OS lifecycle (≤ 300 s):** process-group cancellation, a deadline, an RSS limit breach, and lease removal, with the resource-sampler gap ≤ 0.5 s while a boundary B pass is deliberately slowed (for example by a large fixture) on the main thread.
- **One stdlib contention stress (≤ 120 s), no retry:** the same Python-arithmetic contender as before. The pass criteria are now: the sampler gap stays ≤ 0.5 s, boundaries are honoured, and there are no integrity false positives. There is no 5 s criterion.
- **One startup-only identity rehearsal (≤ 120 s, RSS and MPS each ≤ 6 GiB, outputs written read-only to a new directory):**
  - real interpreter and imports, post-import B pass, `check_frozen`, origins;
  - N ≥ 5 B-boundary pass timings to drive the F/C rule;
  - no D1 deserialization, no environment construction, no inference, no gradient.
  - The parent judges whether this fits the existing authorization; I believe it does, as relevant validation.
- **Freeze and JSON manifest checks (≤ 60 s).**

The one D2 run then uses the unchanged 7200/7140/7170 s budgets and the 10 s shared cleanup. D1 restoration and the 64-row entry control run before any gradient.

## 9. Risks

- Same-user writers are only constrained by the attestation.
- Transient windows are larger than before.
- The runtime and native manifest is not a transitive OS closure.
- The level C rule is a cost heuristic.
- Pre and postflight time across about 290 MB counts against the finite budget and may honestly fail it.
- The r1 per-update figure is a coarse reference.
- This design produces no ML performance evidence.
