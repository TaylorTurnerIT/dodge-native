# Learned model weights

These files are research artifacts. They are copies of learned weights from the outer `hnn/` study directory. The exact-engine lookahead remains the judge. A model passes only when it matches exact-engine results on the same seeds.

The files are JSON. Copies are byte-identical to the outer files named below.

## Files

| File | What it is | Loaded by | SHA-256 | Size (bytes) |
| --- | --- | --- | --- | --- |
| `physics_events.json` | **Current model.** Learned port-Hamiltonian physics plus the event layer (collision, blast, rectangle, spawn, bounce curve, kamikaze acceleration and rate). | `--physics-model PATH` on the `dodge-danger` binary. The examples `explain_death`, `bounce_probe`, `pixel_dump`, and the `fidelity_*` probes take the model path as an argument. | `930dbdc32b3a47d3221f658572e87fc94ea6b21a405524fad652df6d551fd534` | 134859 |
| `physics_events_v1.json` | Older event-layer version. Has collision, blast, rect, and spawn. | Same as `physics_events.json`. | `a8af88a9882b3fb423a319b80335c11a212d28607ee6f26f75a25c58bb921f54` | 133877 |
| `physics_events_v2.json` | Older event-layer version. Has collision, blast, rect, and spawn. | Same as `physics_events.json`. | `e45c59a183b2d81e87b50676442e6a3849711cf59d46302bf1d6effbef2553bb` | 133876 |
| `physics_events_v3.json` | Older event-layer version. Adds the bounce curve. | Same as `physics_events.json`. | `e44fe772d97a889dbafd82327616d673981be41fde09a516969a848dcfba2e1b` | 134700 |
| `physics_events_crush.json` | Experimental event-layer version. Has a `crush` section in place of the kamikaze terms. | Same as `physics_events.json`. | `ad950024b18b100549c4e9a2dec2ac417e89bc11f576ed2ff7687c2a9eb31e93` | 167022 |
| `physics.json` | Physics only (`layers`, `gamma`). No event layers. | Same as `physics_events.json`. | `6a6713499daaa486ddda63b5a736b986e9b6201eb6f202ff8d5e89245ad589a2` | 101841 |
| `noise-estimator-v2.json` | Learned observation estimator trained with noise. Format `observed_estimator_v2`, history 9. | Environment variable `HNN_OBS_MODEL=models/noise-estimator-v2.json`. Not the default. | `ced209c994f0714decb9b01a8d8bd430a22836fced7c07c1692ba4c809c47fb1` | 31735 |

## Not copied

- The default observation estimator is `crates/dodge-danger/models/observed.json`. This file is already tracked in git. It has format `observed_estimator_v1`, history 5, and SHA-256 `848ebf5f64e1ca18b53d39640ebb33ae72f822e73541e7222205a79f3ae423fa`. It loads when `HNN_OBS_MODEL` is unset.
- The outer copy `hnn/data/observed-estimator-v1.json` is byte-identical to that file. It was not copied again.

## Notes

- The planner reads the physics file only from a command-line path. No environment variable selects it.
- The default `HNN_OBS_MODEL` path is in `crates/dodge-danger/src/observe.rs`.
- Results from these weights are measured on the seed sets named in the pull request. Results on other seeds are unverified.
