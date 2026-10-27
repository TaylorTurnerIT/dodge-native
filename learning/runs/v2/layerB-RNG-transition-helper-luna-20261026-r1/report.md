# Layer B RNG transition helper: preparation record

Status: inert preparation only. No seeds reserved or applied; no production runner binding or launch authority.

## Deliverables

- `transition.py`: injected restore/reseed/controller contract. Requires explicit six-field seed mapping, MPS backend, exact accepted-348 fingerprints, and trusted restore callback. It checks CPU then MPS seed read-back and verifies model/Adam fingerprints survive reseeding. It changes optimizer group LR only.
- `test_transition.py`: six standard-library-only fake API tests. No torch, NumPy, checkpoint, native module, environment, game, or training imports.
- `seed-vectors-successor-metadata.json`: corrected parent vectors with finite prior-master rejection list extended by `5562881586070242562` and `4200000001`; 64 parent episode indices, per-slot rejection counters and first actual seeds, and exact five-range proposed exclusion union.
- `controls.log`: passing test output.

## Transition contract

Restore accepted phase 348 only after checking model `b106e8e1ef0645b357ae8877587e2668aa239435c845223dd9481b6fa3ad399f`, Adam `29108e8441b859f02e149b8e52e8cb9d36bbe8d739eef8a7435ab392be4c523e`, and RNG `831d8fa20b4b9aca009382ccb69f9516336b83540850d86b5cdc53a07ba380ad`. Recheck after trusted restore. Then seed Python and NumPy, call `torch.manual_seed(torch_cpu_global_seed)`, then `torch.mps.manual_seed(action_sampler_torch_mps_seed)`. Torch CPU seeding also seeds MPS on the pinned implementation, so reverse order is invalid. Recheck model and Adam after reseeding. Read back both torch generator seeds as contract evidence.

The pair arms share one explicit vector and seed once per run, not per update. Arm A uses constant `3e-5`. Arm B uses a new origin at cumulative update 396: update 397 starts at `3e-5`; update 456 ends at `1e-5` across 60 updates. Preserve old controller provenance: origin 372, horizon 60, completed 24, saved LR `2.2203389830508474e-05`; never apply that old origin to the new schedule. Future environment construction must use the exact five-range union in the successor metadata. This is a future separately registered namespace, not continuation of the same RNG stream.

## Source citations and findings resolved

- Pinned `ppo.py`: action sampling at line 312; CPU shuffle at line 474; SHA-256 `b3cef91b1293056e9d1820a94fd5730accae4c5728d23566857a6c3a0e1eeac5`.
- `seed.rs`: normalized training seed derivation at lines 77-82; SHA-256 `239cb9d88a61fff7d63c3c13c80e4552caafe814729160f8fb2948d3c1498832`.
- `torch/random.py`: CPU `manual_seed` also seeds MPS; SHA-256 `0b2bd65c8fdf324e00ed2c64e7b06ca5d5ff96053001055c86352c0b3668d0be`.
- Accepted parent receipt SHA-256: `cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016`.
- Corrected vector parent receipt: standard-library derivation passed; constructor seeds are uint32-valid and 53 episode indices were corrected. This successor preserves those seeds and indices.
- Haiku review F1 addressed in helper order and read-back contract; F2 addressed by distinct 396 schedule origin and preserved 372 provenance; F3 addressed by adding `5562881586070242562` and retaining `4200000001` in finite rejection metadata. F4 addressed with all 64 counters against the five-range proposed union. F5 citations above identify pinned paths and lines. F6 addressed by rejecting missing constructor seed. F7 remains a documented over-restriction in parent derivation; no master seed is checked against episode-only ranges by this helper.

## Verification and limits

`python3 -m unittest -v` passed 6/6 fake API tests. This proves only the Python contract against fake APIs. No real runtime fingerprint implementation or trusted checkpoint restore was invoked. No native source-to-binary proof, Torch/MPS state read-back, environment construction, game, or training was run. Parent finite master-seed history may be incomplete. The proposed exclusion union is not installed; future registration must reconcile it with the native runtime and check all actual seeds at construction. Parent acceptance/lease procedure remains authoritative.
