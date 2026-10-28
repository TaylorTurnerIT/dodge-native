# Parent one-run dispatcher review

**No blocking source findings in the reviewed parent dispatch wrapper for the first uniform registration.** Wrapper SHA-256 was `52f7cd83958de4f0c13a3a1a0683e8cb12f4f902e5b96fa33b52a39049c29bff` before and after review.

## Evidence

- Target index SHA-256: `f4dbde70f0f07b979ac59da010a4339289f0e1259ed59b5be1a070d1ca300eb8`. First uniform registration SHA-256: `7606ee9d46a8e325ef70d1aa5e65b0231b574b086464fc9b2e3ddd93f5daed16`.
- `start_one.py:35-47` hashes the exact index and parent-gates files, selects exactly one run ID, constrains its registration directory to a direct child of the parent execution directory, checks gate pins/status/source hash, and pins the selected registration.
- `start_one.py:49-60` runs r2 static validation, cache checks, hashes the dependency inventory's installed-byte pins, and rejects spent output, claim, marker, dispatch, and parent receipt paths before writing the lease or marker.
- `start_one.py:61-93` checks campaign/inference conflicts and active training hold, installs the registration's exact lease, validates startup state, binds separate source acceptance and canonical launch approval in the envelope, then writes the spent marker and verifies the bound envelope before dispatch.
- `start_one.py:94-137` dispatches one `launch.py` process in its own session, records observer PID/PGID plus registration/envelope hashes, drains progress, waits and reaps the direct observer, and writes the raw parent exit receipt. It contains no retry, next-arm dispatch, audit, or promotion path.
- Parent receipt fields match r2 `audit.py`: `parent-execution.json` supplies observer PID/PGID, registration and envelope hashes; `execution-exit.json` supplies raw observer exit, direct-reap status, and registration hash. R2 audit separately validates worker/observer receipts and clears only the exact lease after durable audit.

## Limits

This is a static review of the wrapper and its first indexed registration, not a dispatch. No gates file was consumed or modified, so this review does not certify its eventual contents or the live state at dispatch time. Parent must pin the exact wrapper, index, selected registration, runtime/source, calibration, dependency inventory, and accepted reviews in its externally hashed gate document. Runtime release parity and actual native/MPS qualification remain separate parent gates. No lease/state writes, marker writes, child process launch, native/Torch/MPS calls, or checkpoint loads were performed.
