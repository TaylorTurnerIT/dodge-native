# Confirmation proof fixture preparation

Owned output copied from `confirmation-proof-wiring-luna-20261026-r1`. Confirmation fixture now builds a complete synthetic R3 ranking registration, six 1,024-row candidate results, summary, successful outer artifact bindings, and selection record through `selection.produce_selection`. It uses only fake fixture candidate pins, source pins, and the existing synthetic accepted-benchmark wrapper.

Added pre-marker rejection coverage for changed nested outer hash, altered locked winner, tampered validator bytes, and winner 348. Existing confirmation tests now pass. Direct test exposed missing `importlib.util` import in supervisor; added that import so externally pinned worker loading works. No other production wiring changed.

Python 3.9.6: 8 focused selection proof tests passed; 24 runner tests passed. See `tests.log`, `source-hashes.json`, and `receipt.json`.

Limits: stdlib synthetic fake-process fixtures only. No actual ranking or confirmation outcomes, runtime/native/Torch/MPS/checkpoint loads, real leases, real markers, real launches, or training. Throughput compatibility remains pending parent review. These preparation tests do not qualify current benchmark timing.
