# Expanded D2 evaluation proposal

Proposal only. No evaluation/training launch, lease relaxation, gate change, or seed reservation has occurred.

| Lane | Proposed work |
| --- | --- |
| Ranking | Evaluate original accepted checkpoints 180/204/276/300/324 and audited348 on the same 1024 frozen seeds. |
| Confirmation | Open a disjoint1024-seed cohort once after freezing the winner and comparator348; require348 parent acceptance first. |
| Training replication | Three matched training seeds per arm, minimumtwo; equal60-update endpoints, operational-best reporting separate. |
| Concurrency | Separate reviewed per-run leases, observers and cancellation; initiallytwo training workers, each retaining6GiB RSS and6GiB MPS caps. |

Ranking uses mean survival, ties earlier update. Report Q1/Q4 as bottom/top256 means, paired uncertainty, caps and death causes. The fixed/linear pair already shares masterseed4200000001; it remains only one matched pair.

Candidate checkpoint and accepted receipt byte hashes are reconciled in proposal.json. The earlier Luna draft pointed to several newly serialized entry copies rather than the original retained checkpoints; this successor uses original receipts. Candidate348 remains full-audit passed but publication pending.

Proposed seeds: ranking0xD1000000..0xD10003FF; confirmation0xD2000000..0xD20003FF. These blocks are disjoint from known B/E/D128, but old training did not reserve them. Audit all historical training ancestry, completed/abandoned/in-flight seed exposure first. Missing proof or collision blocks launch. Install both exclusions in any future registered training configuration before constructing environments. Neither manifest opens outcomes or changes active reservations.

If ranking selects a different checkpoint, confirmation compares it against locked348 on identical seeds; proposed replacement rule is one-sided95% paired-bootstrap lower bound above zero. If348 wins, confirmation reports its independent mean and confidence interval without testing against itself or changing the pointer. No retry, next-best substitution or cohort reuse after opening. Future confirmation claims require fresh blocks and an explicit sequential error policy. This is development validation; B/E qualification and all gates remain unchanged.

Worst case:6144 ranking plus2048 confirmation episodes,147456000 raw frames at cap18000. This is a frame bound, not a timing claim. A separately registered evaluation budget must follow permitted throughput measurement and conservative full-cap projection. It does not spend training updates or its campaign wall budget.

Restore model/Adam/RNG before explicit LR-controller transition. Three new training seeds would pair constant3e-5 against linear3e-5→1e-5 for60updates from the same accepted348. Different average LR means this tests the whole controller choice; add a preregistered constant2e-5 arm only if schedule ordering is the question.

Current host reports48GiB physical memory. Proposed concurrent registry uses unique ownership, atomic lease updates, independent resource samplers, output/cancel/one-shot paths and parent acceptance. Preserve both6GiB per-campaign caps and host headroom; RSS and MPS remain separate, overlapping measures. Existing frozen single-lease guards remain intact.
