"""Preparation preflight. Mocks only parent-owned lease assertion; never launches worker."""
import sys
from pathlib import Path
import runner
registration=Path(sys.argv[1]).resolve()
digest=sys.argv[2]
runner.check_lease=lambda _reg: None
reg,config=runner.load_registration(registration,digest)
print(f"registration valid; pins={len(reg['pins'])}; config_sha256={reg['config_sha256']}; lease_assertion=mocked_only_for_preparation; worker_not_started=True")
