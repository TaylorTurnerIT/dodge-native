"""Repair residual original overwrite found by actual worker AST regression."""
from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent;p=H/'long_d2.py';before=p.read_bytes()
s=before.decode().replace("    result.update(outcome_fields(failure_outcome(error)), error=repr(error))\n    record_primary_failure", "    record_primary_failure")
assert s!=before.decode();p.write_text(s)
(H/'units-03-production-correction.json').write_text(json.dumps(dict(prior_attempt='attempts/units-03',failure="AssertionError: 'cancelled' != 'safety_stop'",cause='Original worker_failure upfront result.update remained before first-failure recorder',repair='Remove that one overwrite; record_primary_failure exclusively owns outcome/error',controller_before_sha256=hashlib.sha256(before).hexdigest(),controller_after_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),justification='New affected actual-worker regression exposed in-scope implementation defect; exact failed source/log/AST/output retained. No limits, trigger, pins, learner changes or stress retry.',next_attempt='attempts/units-04'),indent=2)+'\n')
