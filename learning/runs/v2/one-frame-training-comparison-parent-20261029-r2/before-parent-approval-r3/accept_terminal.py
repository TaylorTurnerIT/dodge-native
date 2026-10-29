"""Read-only terminal receipt acceptance helper. Does not release leases or promote weights."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def need(ok,message):
    if not ok: raise ValueError(message)


def validate(audit_path,audit_sha256,execution_path,execution_sha256,registration_path,registration_sha256):
    for path,digest in ((audit_path,audit_sha256),(execution_path,execution_sha256),
                        (registration_path,registration_sha256)):
        need(sha(path)==digest,'terminal acceptance input hash differs: '+str(path))
    audit=read(audit_path); execution=read(execution_path); reg=read(registration_path)
    need(audit['schema']=='one_frame_training_comparison_terminal_audit_v1'
         and audit['run_id']==reg['run_id'] and audit['registration_sha256']==registration_sha256,
         'terminal audit lineage differs')
    need(execution['raw_observer_exit_code']==0 and execution['observer_directly_reaped'] is True
         and execution['registration_sha256']==registration_sha256,'parent execution receipt is not successful')
    expected=('qualification_complete' if reg.get('phase')=='qualification' else 'complete')
    need(audit['evidence']['status']==expected and audit['lease_cleared'] is False
         and audit.get('phase',reg.get('phase','formal'))==reg.get('phase','formal'),
         'terminal evidence is incomplete or audit claims lease release')
    need(audit['promoted'] is False and audit['automatic_selection'] is False
         and audit['training_eligible'] is False,'training authority disposition differs')
    phase_root=(Path(reg['execution_root']) if reg.get('phase')=='qualification' else
        Path(registration_path).resolve().parent)
    release=read(phase_root/'lease-release.json')
    need(release['schema']=='one_frame_training_comparison_lease_release_v1'
         and release['run_id']==reg['run_id'] and release['registration_sha256']==registration_sha256
         and release['parent_terminal_audit_sha256']==audit_sha256
         and release['lease_value_after_release'] is None,
         'exact phase lease release receipt differs')
    return dict(status='terminal_evidence_valid_for_parent_acceptance',run_id=reg['run_id'],
        launch_authority=False,exact_phase_lease_release_verified=True,
        promotion=False,automatic_selection=False,training_eligible=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('audit','audit-sha256','execution','execution-sha256','registration','registration-sha256'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args();print(json.dumps(validate(a.audit,a.audit_sha256,a.execution,a.execution_sha256,
        a.registration,a.registration_sha256),sort_keys=True))
