# Historical Opus teacher probes

These are verbatim scripts and raw measurements from the Opus 5.5 investigation on October 24, 2026 UTC. They support the reusable [investigation methodology](../../investigation-methodology.md) and the [Dodge diagnosis](../../teacher-failure-diagnosis.md).

| Artifact | Purpose |
| --- | --- |
| [opus-probe.py](opus-probe.py) | Compare fresh, supervised, and PPO models on matched states; inspect scale, routing, gradients, and counterfactual responses |
| [opus-labels.py](opus-labels.py) | Test whether avoidance labels depend on enemies |
| [opus-representation-probe.json](opus-representation-probe.json) | Raw representation and intervention measurements |
| [opus-label-enemy-dependence.json](opus-label-enemy-dependence.json) | Raw target-dependence measurements |
| [manifest.json](manifest.json) | File sizes/hashes, checkpoint identities, model-source hash, and native binary identities |

The first script used 40 observations from one controller trajectory and one middle observation for counterfactuals and gradients. It modified the first enemy, despite a nearest-enemy comment. Its gradient scalar was `std(logits)`, and its projected-feature variation used all 32 fields. The second script's uncertain note about rectangles is historical commentary: rectangles occupy a separate state field, and the heuristic separately excludes enemy-list entries with personality `kind >= 2`.

The scripts contain fixed run paths, set process-global RNG state, and write to fixed output names. They are historical examples rather than production utilities. Reproduction requires compatible source, environment, schemas, and the separately retained checkpoint weights. Use a new output directory and explicit source/configuration identities for a new investigation. The archived checkpoint hashes identify the original inputs; no checkpoint weights or current gameplay qualification are included here.

Opus reported about 1.20 and 2.92 seconds elapsed wall time for the two probe scripts. These are diagnostic timings, not isolated performance measurements. Native failure traces and synthetic overfit training were conducted by independent parent-team agents, rather than by these scripts.
