"""Validate or execute exactly one later parent-registered progressive1000 run."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import contracts as c


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration',required=True)
    parser.add_argument('--registration-sha256',required=True)
    parser.add_argument('--source-acceptance',required=True)
    parser.add_argument('--source-acceptance-sha256',required=True)
    parser.add_argument('--started',type=float,required=True)
    parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args()
    reg,context=c.preflight(args.registration,args.registration_sha256,args.source_acceptance,args.source_acceptance_sha256,args.started)
    if args.validate_only:return 0
    import worker
    return worker.execute(reg,context,args.registration_sha256,args.started)


if __name__=='__main__':
    raise SystemExit(main())
