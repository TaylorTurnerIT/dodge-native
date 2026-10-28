"""Read-only terminal audit for an externally authorized run."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import binding as b
import terminal

def audit(registration_path, registration_sha256, control_path, out_path=None):
    b.need(b.sha(registration_path)==registration_sha256,"registration digest differs")
    reg=b.read(registration_path)
    out=Path(out_path or reg["output"])
    worker=b.read(out/"worker-result.json")
    control=Path(control_path)
    observer=b.read(control/"observation.json")
    execution=b.read(control/"execution-result.json")
    result=terminal.validate_outputs(reg,worker,registration_sha256)
    b.need(observer.get("status")=="completed_pending_parent_audit","observer did not finish cleanly")
    b.need(observer.get("raw_worker_exit_code")==0 and observer.get("raw_observer_exit_code")==0,
           "raw worker/observer exit differs")
    b.need(execution.get("raw_worker_exit_code")==0 and execution.get("raw_observer_exit_code")==0,
           "execution result raw worker/observer exit differs")
    accounting=terminal.accounting(out,worker,strict=True)
    result["accounting"]={k:v for k,v in accounting.items() if k!="completed_episode_rows"}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--registration",required=True)
    p.add_argument("--registration-sha256",required=True);p.add_argument("--control",required=True);p.add_argument("--output")
    a=p.parse_args();print(json.dumps(audit(a.registration,a.registration_sha256,a.control,a.output),sort_keys=True,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
