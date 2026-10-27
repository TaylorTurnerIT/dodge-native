# Long-D2 supervisor repair r2

This is preparation for a fresh parent frozen review. No production campaign,
lease, Torch/native import, teacher deserialization, inference, gameplay or
training was performed. The exact registered experiment remains
`v2-m3-long-D2-20261024-r1`, output `postovernight-long-D2-campaign-r1`, seed
`5562873868232098305`, with a 7,200-second absolute budget and the exact successful
D1 checkpoint SHA256 `ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f`.
All failed D2 weights remain ineligible. No resume or retry exists.

The parent revision changes only the controller path and registration timestamp.
This helper binds `postovernight-long-D2-r1-protocol-r2.json`, raw SHA256
`f662a4aba18e144098faeb01d398b67f489aea7549a9ebe4a5959f993e1cff09`.
The config raw SHA256 remains
`2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db`.
The previous protocol, r1 candidate, both independent reviews, all historical
artifacts and their identities remain intact.

## SUP-001: publication authority

The actual Guard remains active while normal artifact hashes and terminal writes
run. Its supervisor observation stream is memory only. After owned worker reaping
and positive group-absence proof, the supervisor writes and closes one
`supervisor-guard.jsonl` snapshot. Later samples never write that file. Thus no
manifest-bound log has a live writer during hashing. The terminal receipt labels
the snapshot's scope and records publication resource observations separately.

Resource/lease sampling and full input verification use separate threads and
locks. Full byte hashing cannot suppress the <=0.5-second resource/lease monitor.
Full input checks retain the <=5-second bound, including their own duration.
Both monitors latch failures. Publication checks authority before/after hashes
and writes, with forced full verification immediately before terminal authority
and after its write. After publication alarm restoration, monitor closure and
memory-stream closure, synchronous full checks revalidate inputs and lease,
including after the last terminal write. Sampling gaps and the absolute deadline
still fail closed. Any authority loss revokes the complete terminal and manifest;
only explicit failure persistence remains.

The complete pin set includes original 75 sources, original runtime/foundation,
new helper/test source, both protocol versions, unchanged config, new identity,
D1 terminal chain, readonly capsule and original-only r1/review references.
Loaded `dodge_rl` modules retain explicit original package origins, hashes and
capsule-mirror checks. Unchanged historical `check_frozen` receives the original
D2 config/root. Unchanged `validate_transition` receives only the exact D1 anchor.
Neither historical proof authorizes the new budget. No legacy validator,
Experiment constructor or legacy Guard is bypassed.

## SUP-002: one cancellation latch

One effective outer SIGINT/SIGTERM latch covers worker ownership, cleanup,
publication, alarm restoration, monitor/stream closure and final decisions.
Nested publication contexts borrow that latch and never restore its handlers.
Every delivered request increments the same counter. Handler restoration is
signal-masked; pending requests join the same latch before unmasking. The
supervisor revalidates full authority after handler restoration while signals
remain masked, then reads the latch again after its outer context exits and revokes
completion when a request arrived during restoration.

Normal work must finish before T0+7,200; T0 precedes ordinary imports and worker
spawn. The worker remains bounded by T0+7,140. Failure-only owned cleanup remains
<=10 seconds. RSS and MPS each retain a separate 6 GiB limit. A blocked worker
remains bounded by the independent supervisor alarm. Exit 0 means complete D2
progress gate pass; exit 2 means complete budget closure below gate; exit 1 means
failure. No result opens D3/B/E/student work or teacher qualification.

`Learner`, all schedule logic, model/Adam/RNG restoration, entry control,
environment construction, counters, ML call sites, rewards and gates remain
byte-identical. The worker receipt adds only a scope label: inherited
`run_context.consumed_wall_seconds` belongs to historical D1 and never defines the
new budget. Exact source comparisons and the full r1-to-r2 diff are delivered.
Actual MPS restoration and entry equality remain future mandatory runtime gates.

## Evidence and freeze

The original 70 synthetic methods remain, with 13 publication methods. New
probes execute actual `supervise`, actual Guard and owned stdlib OS workers.
They cover both completion outcomes, delayed hashes, late input/lease changes,
before/after manifest and terminal writes, final checks, monitor/stream closure,
real subprocess SIGINT and SIGTERM at outer publication-alarm exit, and the outer
latch's own handler restoration. Probes track open output writers at every hash,
verify final manifest bytes, record monitor gap bounds, and positively prove owned
group absence. Subtests are not counted as separate test methods.

Fourteen inherited deliberate controls and three exact-r1 regression groups must
fail by AssertionError, never import/API errors. The r1 comparison imports its
exact original helper without path rewriting or API adaptation. All attempts,
expected failures, sources, logs and synthetic output receipts remain retained.
`test-receipt.json` records fresh final counts and source hashes.

`freeze.py` is stdlib only. Identity pins every active root helper/test Python
source. Retained attempt/mutant sources belong to the preparation artifact
inventory, not the active execution source list. Historical r1 and review files
are original-only immutable references; the old capsule/logs are never copied
into the new execution capsule. Original 75 package/core mirrors and the new
helper sources are freshly copied, verified and sealed readonly.

Raw identity document hash differs from canonical checkpoint semantic identity
hash. Identity excludes its own document hash and the capsule manifest; the
manifest includes identity and excludes itself. `invocation.json` gives exact
argv/cwd/environment. `required-lease.json` gives the strict 15-field lease;
only the parent may activate it after fresh frozen review. Task IDs belong
outside that lease. Pure preflight creates no production output.

`finalize_preparation.py` runs only after redirected logs close. It verifies
protected before/after hashes, frozen preflight, source equality, tests and control
receipts, then writes the final inventory. That inventory excludes only itself.
Parent must separately observe raw exit and actual wall time; receipt timing
excludes its own write and process exit. This preparation proves no actual
Torch/native/MPS runtime behavior, learning performance or qualification.

The first r2 sealed preparation is retained in `capsule` with its receipts and
source in `attempts/pre-outer-closure-repair`. Final execution capsule is
`capsule-final`; final receipts bind only that capsule. The first seal exposed
an additional SUP-001 outer-restoration input/lease gap during final audit.
Four new actual-Guard OS cases discriminate that gap; no campaign was launched.

A synthetic blocked-worker check exposed a pending SIGALRM restoration race.
The failed exit 142, log and exact source remain retained. Final alarm teardown
masks, disarms and consumes pending SIGALRM before restoring the prior handler.
Failure paths start no new normal verification or alarm after the deadline.
