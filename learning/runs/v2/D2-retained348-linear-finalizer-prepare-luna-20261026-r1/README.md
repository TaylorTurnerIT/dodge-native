# Retained348 parent finalizer preparation

This directory contains an inert, parent-only finalizer and CPU synthetic controls. It does not publish receipts or change the lease during preparation.

Haiku r3 review: no blockers. The frozen parent reconciliation is at `learning/runs/v2/D2-retained324-linear-parent-terminal-audit-20261026-r1/review-reconciliation.json` (SHA-256 `4b4e51ede5def51b44635926cbd4c0ae4345e8c68b165f2e8e9a8925c8f75b06`). The finalizer verifies this exact file, the registration, all 13,857 pins, full audit and binding, parent full-audit receipt, all six candidates, both empty cache prefixes, terminal process absence, and the exact active lease before acceptance.

Parent must copy `finalize_parent.py` byte-for-byte into `learning/runs/v2/D2-retained324-linear-parent-terminal-audit-20261026-r1/`, then invoke that copy once with the registered Python interpreter and `-B`. The script refuses invocation from this preparation directory. Importing it is inert. Do not rerun after partial output; preserve receipts for parent review.

At explicit parent invocation only, it loads candidate348 on CPU through the registered checkpoint loader, checks model/Adam/RNG fingerprints and schedule state, writes exclusive parent receipts, and atomically updates the ledger after a fresh exact-lease/cancel/source/cache guard and byte comparison. It never launches training, evaluation, MPS, or a campaign retry.

Expected selected candidate: update348/local24/cumulative396, checkpoint SHA-256 `b95228e5e2934c915597595f7eb3c8618ee5f7c2182dde1481a060d01c270369`, mean3098.125, Q1 867.0625, Q4 6003.875. Competence is true; qualification and stage promotion are false. Endpoint384 remains discarded. The provisional mean gain is not a scientific schedule-causality claim.
