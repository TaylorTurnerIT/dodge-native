# Parent integration proposal

Preparation only. Do not apply this patch to the accepted benchmark source. The parent may transplant the adapter after review and registration-format alignment.

## Replace weak `worker.validate_selection`

Current function checks record/refs and checkpoint hashes, but not comparator or run provenance. Future integration should pass externally pinned registration/result paths and hashes to `selection.validate_selection_record`:

```python
from ranking_selection.selection import validate_selection_record

def validate_selection(reg, registration_path, registration_sha256, result_bindings):
    locked = reg.get('selection_record') or {}
    if not locked.get('path') or not locked.get('sha256'):
        raise RuntimeError('confirmation selection record path/hash required')
    return validate_selection_record(
        locked['path'], locked['sha256'], registration_path, registration_sha256,
        result_bindings, reg['run_id'], reg['source']['evaluator_sha256'],
        reg['runtime']['aggregate_sha256'], reg['cohorts']['ranking']['sha256'],
        reg['cohorts']['ranking']['manifest_sha256'])
```

Names for runtime/cohort/manifest pins are placeholders; parent must map them to actual registration format and must reject absent pins. `result_bindings` must come from parent-pinned paths and hashes, not paths supplied by selection JSON. Do not invoke confirmation when winner is 348.

## Replace unpinned supervisor import

`execute_once.py` currently imports `from worker import validate_selection` in preflight and postflight. Load the worker from the already hash-checked `--worker` path with `importlib.util.spec_from_file_location`, verify the resolved module path equals the pinned path, then call the pinned module's validator at both sites. Keep the same pinned module object for both calls. Do not edit the accepted `execute_once.py` in this preparation.

## Registration/throughput gate

M-5 remains separate. Before ranking preparation can be launch-eligible, parent must compare benchmark outer receipt worker/evaluator hashes and runtime member map with ranking registration. This adapter requires explicit externally supplied evaluator/runtime/cohort/manifest pins and exact matching identities in each raw candidate result. It does not infer these pins or qualify throughput equivalence.

## Authority and limits

Selection is selection-only. Never change parent-accepted update 348 based on ranking. A non-348 winner is only eligible for a separate parent confirmation gate; 348 yields `no_confirmation`, with no invocable confirmation record. No ranking outcomes or confirmation artifacts were read or created.
