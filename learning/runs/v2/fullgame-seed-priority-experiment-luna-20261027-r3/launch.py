"""Parent-approved one-shot entry point; own code never creates markers or leases."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import binding as b
from execute_once import execute

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--envelope",required=True);p.add_argument("--envelope-sha256",required=True)
    a=p.parse_args();env,reg=b.load_envelope(a.envelope,a.envelope_sha256)
    b.verify_bound(env,reg,preflight=True)
    return execute(a.envelope,a.envelope_sha256)
if __name__=="__main__":raise SystemExit(main())
