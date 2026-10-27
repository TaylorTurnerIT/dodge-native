# Frozen boundary integrity r3 review

Verdict: **changes required**. Three P2 source/consumer findings appear in `findings.json`.

## Identity and scope

The initial byte inventory was captured before discriminators. All eight supplied candidate hashes and the protocol/policy hashes matched. `input-hashes.json` retains expected and observed values. `context-snapshot/` preserves read-time required authorities, including the complete contextual parent state. Full implementation plan, specification, state, accepted policy, diagnosis and policy plan were read. Latest supplied exact r3 targets take precedence over lagging state fields.

`end-snapshot.json` rechecked 146 frozen candidate/capsule files, excluding parent-owned `attempts/`, and the ten target pins, with no mismatch. Initial broad byte inventory also included metadata hashes of then-existing parent attempt files; those mutable files are not authority, source equality, or final validation evidence. Their content/results were not used to infer parent OS completion. No mutable parent state hash was treated as an immutable execution input.

## Source checks

`static-source-audit.json` independently records exact protected-block equality against both R4 and the rejected guard preparation, including the worker ML try body, unchanged `check_module_origins`, Learner, Schedule, run_schedule, restoration/entry helpers and configuration helpers. Current bytes of all 75 original semantic-source files matched their declarations and B classification. Config hash, master seed and D1 checkpoint hash matched; checkpoint bytes were only hashed, never decoded.

Classification is B=235, R=37, A=9998. All 10091 historical full path/hash bindings appear exactly once, preserving the 9870/9675 retained unions. No canonical class/hash conflict was found. Foundation identity's acceptance, M2 frozen identity, build receipt, executable and interpreter dependencies are B. This is a declaration/source audit plus the specified protected-source hash checks; it is not a new complete R/A endpoint execution.

The source runs actual B bytes/capsule/membership checks at forced boundaries; imported workers call genuine original check_frozen, unchanged project origins and added runtime/path/cache checks. Nonforced callbacks remain safety-only. Full R/A members are checked by the outer endpoint verifier before spawn and after owned absence, with no five-second age predicate. The DAG excludes root envelopes from leaf self-hashing and uses external registration/parent pins. Original paths and the cooperative no-writer assumption remain explicit. Native discovery is bounded Torch/NumPy/CPython/libpython provenance, not a whole-OS/transitive-memory attestation.

Source ordering preserves model/Adam/RNG restoration before environment construction and exact 64-row, nine-field entry control before update/gradient. No runtime restoration, entry behavior, native allowlist adequacy under real imports, performance, training gate, or campaign acceptance was established here.

## Reproducible findings

1. **BOUNDARY-R3-WORKER-DESCRIPTOR**, controller line 938. Exact extracted `worker_failure` rejects its own earlier catch descriptor when handed an ordinary exception. The proof reaches no ACK and initializes no cleanup pool. Logs retain the deterministic source-clock values. Main's fallback remains a raw failure path, but its initiating reason is the newly thrown descriptor error.
2. **BOUNDARY-R3-CONSUMER-REAP**, executor line 512. Exact extracted `accept_observed`, real JSON/hash/summary checks and owned file fixtures return true with both wait reports absent, and separately with both raw reports failed/not reaped. Raw outer exit 1 remains rejected. This demonstrates the actual consumer predicate's missing requirement; the launcher producer independently validates real waits, and no real process was launched by this proof.
3. **BOUNDARY-R3-INNER-PUBLICATION-ORDER**, controller lines 1337-1338. Static AST output shows optional telemetry precedes mandatory inner failure publication. There are zero calls to `failure_publication` in the controller. The outer helper repair therefore does not establish inner wiring. Blocked optional IO can consume the allowance before any mandatory attempt. This is source ordering evidence, not a new OS suppression measurement.

## Execution and limitations

No production unit suite, OS lifecycle case, contention stress, startup rehearsal, ML/native import, checkpoint decoding, inference, gradient, training campaign, lease/scheduler operation, provider/delegation call, commit, PR, deployment or message was performed. All writes belong to this new review directory. Existing 21-method and freeze successes are supplied parent context only. Parent owns final attempt-11 OS reconciliation and every later validation decision.

There were four small source-extracted discriminator attempts: worker timestamp, exact consumer, and two inner-ordering fixtures. Consumer proof has retained raw exit 0. Worker proof's combined shell exit is 0, but its individual Python exit was not independently retained; final confirmation output and empty stderr are preserved. The two inner fixtures are explicitly limited: both traced the relevant order, but omitted dependencies in the extracted namespace prevented the eventual receipt. The second's added final assertion exposed that with raw exit 1. No further inner fixture run followed. These failures are retained, not counted as passing receipt tests, and do not prove acceptance bypass or actual IO suppression. `proof-inner-fixture-correction.md` records the intermediate correction; `findings.json` records the remaining missing os dependency.

The source consumer proof and source finding are distinct from actual runtime/process acceptance. The review cannot accept training, transfer historical pass counts, qualify the teacher, or reconcile the parent's in-flight results. No finding treats the intended removal of fixed five-second integrity/revisit guarantees as a bug.
