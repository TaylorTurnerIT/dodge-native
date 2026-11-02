# DODGE-075 exact source review request

Review the current DODGE-075 source and registration at the exact committed source hashes. Check new run, output, and owner identities; all 30 source pins; all 60 input pins; both route source pins; authority; `host_driver.py`; the single staging contract; trusted readback ordering; safe extraction; fresh directory creation; and read-only preflight gates.

Confirm that `stage_delivery.py` reads back the exact remote archive, stage script, and contract names, byte counts, and SHA-256 values before it executes the remote stage script. Check that archive-name mismatch and stale-script tests exercise the production verifier. Check that no active source path, guard path, claim identity, or lease identity targets DODGE-074. The inherited test fixture must remain byte-identical, including its historical 074 references; it is not run from the successor packet.

Reuse accepted DODGE-074 algorithm, recipe, native, controller, and lifecycle evidence where bytes and scope match. Review only the new registration, authority bindings, identities, packaging, delivery, extraction, and staging-gate delta. Do not claim that remote readback, M1 capacity, runtime, model loading, or training occurred. DODGE-075 has explicit inherited execution authority, but this source review and packet setup do not invoke it.

The uncommitted `review.json` and `SOURCE_COMMIT.json` are pending placeholders. Replace them only with the exact accepted review and final source-commit binding, then rebuild and rehash the archive and contract. Do not execute the SSH delivery command as part of this review.
