"""Pre-validation refinement provenance; only owned sources."""
from pathlib import Path
H=Path(__file__).resolve().parent
s=(H/'long_d2.py').read_text()
s=s.replace('''        with verification_component('legacy_frozen_rebuild'):
            if imported:''','''        with verification_component('legacy_frozen_rebuild'):
            if imported:''')
s=s.replace("    record_primary_failure(result, error)\n    permission['failed']", "    record_primary_failure(result, primary_error(error, guard))\n    permission['failed']")
s=s.replace('\ndef record_primary_failure(result, error):','''\ndef primary_error(error, guard):
    # A monitor failure can precede delivery to the main thread. Preserve it
    # only when it predates the first recorded signal; user cancellation first
    # remains cancellation. This is ordering evidence, not inferred user intent.
    first_signal = None if life.ACTIVE is None else life.ACTIVE.first_at
    if (guard is not None and guard.failure is not None and guard.failure_at is not None
            and (first_signal is None or guard.failure_at <= first_signal)):
        return guard.failure
    return error


def record_primary_failure(result, error):''')
# Guard-like ACK fixture did not expose failure before the new ordering check.
(H/'long_d2.py').write_text(s)
s=(H/'test_worker_ack_contract.py').read_text().replace('guard=types.SimpleNamespace(failure_at=0.0,','guard=types.SimpleNamespace(failure=None,failure_at=0.0,')
(H/'test_worker_ack_contract.py').write_text(s)
s=(H/'synthetic.py').read_text().replace("        guard.close()\n        result.update", "        guard.close()\n        guard.persist_timing(output/'worker-verification.jsonl',args.started+c.WORKER_SECONDS)\n        result.update")
(H/'synthetic.py').write_text(s)
