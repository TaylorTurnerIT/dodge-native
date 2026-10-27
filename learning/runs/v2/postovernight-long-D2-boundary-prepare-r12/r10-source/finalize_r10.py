"""Evidence-only closeout after the one stage. Never edits candidate source."""
from pathlib import Path
import datetime
import difflib
import hashlib
import json
import os
import subprocess
import time
H=Path(__file__).resolve().parent
ROOT=H.parents[3]
EXCLUDED={'source-manifest.json','evidence-manifest.json'}

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def save(path,value):path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
    unit=H/'unit-stage'
    raw=json.loads((unit/'raw-result.json').read_text())
    suite=json.loads((unit/'suite-result.json').read_text()) if (unit/'suite-result.json').exists() else None
    command=json.loads((unit/'command.json').read_text())
    source=json.loads((H/'source-manifest.json').read_text())
    stable={name:sha(H/name)==record['sha256'] for name,record in source['files'].items()}
    base=json.loads((H/'input-pins.json').read_text())
    base_equal={name:sha(ROOT/name)==digest for name,digest in base['base_pins'].items()}
    authority_equal={name:sha(ROOT/'learning/runs/v2-orchestration'/name)==digest for name,digest in base['authority_pins'].items()}
    success=(raw.get('raw_exit')==0 and not raw.get('timed_out') and suite is not None and suite['successful']
             and all(stable.values()) and all(base_equal.values()) and all(authority_equal.values()))
    differences=[];changes=[]
    for name in sorted(source['files']):
        path=H/name
        if '/' in name:continue
        if name=='protocol-r7-proposal.json':old=H/'r9-source/protocol-r6-current.json'
        else:old=H/'r9-source'/name
        before=old.read_text() if old.exists() else ''
        after=path.read_text()
        if before!=after:
            differences.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
                fromfile='r9/'+(old.name if old.exists() else '/dev/null'),tofile='r10/'+name))
            changes.append(dict(path=name,base_sha256=sha(old) if old.exists() else None,
                candidate_sha256=sha(path),added=not old.exists()))
    (H/'candidate.diff').write_text(''.join(differences))
    save(H/'change-manifest.json',dict(files=changes,diff_sha256=sha(H/'candidate.diff'),
        unchanged_fixtures=['original-source','r6-source'],base_copies='r9-source',complete_for_candidate_source_manifest=True))
    save(H/'end-verification.json',dict(source_unchanged_after_stage=stable,base_pins_still_equal=base_equal,
        authority_pins_still_equal=authority_equal,mutable_state_rechecked=False,no_post_failure_patch_or_retry=True))
    end=datetime.datetime.now(datetime.timezone.utc)
    # The parent registration predates all context reads; it is the conservative wall origin.
    # Keep raw launch structure in inputs; use the task's parent timestamp when available.
    elapsed=(end-datetime.datetime.fromisoformat('2026-10-25T02:30:10.021085+00:00')).total_seconds()
    result=dict(schema='long_d2_boundary_r10_implementation_v1',candidate=str(H.relative_to(ROOT)),
        status='prepared_unit_stage_passed_parent_review_pending' if success else 'stopped_on_first_unexpected_failure',
        completed_at_utc=end.isoformat(),preparation_and_stage_elapsed_seconds_parent_origin=elapsed,
        preparation_cap_seconds=1800,unit_stage_cap_seconds=300,unit=raw,suite=suite,
        command_path='unit-stage/command.json',unit_argv=command['argv'],
        unit_logs=['unit-stage/stdout.log','unit-stage/stderr.log'],
        sources_unchanged_after_stage=all(stable.values()),source_ownership='released;frozen_for_immutable_review',
        source_manifest_sha256=sha(H/'source-manifest.json'),candidate_diff_sha256=sha(H/'candidate.diff'),
        proposed_protocol_sha256=sha(H/'protocol-r7-proposal.json'),
        future_external_protocol='learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r7.json',
        controller_sha256=sha(H/'long_d2.py'),executor_sha256=sha(H/'long_d2_executor.py'),
        unchanged_transport_and_failure_pool_sha256=sha(H/'lifecycle.py'),
        fixes=['A validated abnormal worker wait source before IPC/probe/file IO; same source recovered in outer',
               'B isolated monitor safety/cancel/reap/group duties; bounded diagnostics; deadline outside fallible duties',
               'C attempted/acked/failed boolean start ACK state; one attempt; failure before retirement',
               'D independently registered phase and positive prerequisites; explicit wrong-entry rejection'],
        source_equalities='unit tests compare actual protected blocks and all successful consumers to r9/r6/historical bases',
        config_sha256='2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db',
        master_seed=5562873868232098305,D1_sha256='ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f',
        registration_published=False,freeze_performed=False,lease_acquired=False,OS_matrix_executed=False,
        probes_executed=False,stress_executed=False,startup_rehearsal_executed=False,training_launched=False,
        ML_native_imports_executed=False,checkpoint_decoded=False,delegation_or_provider_calls=False,
        retries=0,post_failure_patches=0,automatic_follow_on=False,
        write_scope='new owned candidate directory only; no universal OS write attestation',
        limitations=['Pure stdlib synthetic class evidence only; no real process lifecycle or transport closure proof.',
            'No OS, performance, reliability, runtime, training acceptance or teacher qualification.',
            'Physical worker exit time remains unknown; timestamp is successful direct waitpid observation.',
            'Late failure attribution proves order under positive fixture prerequisites, not exclusive causality.',
            'No historical count or acceptance transfer. Parent owns fresh freeze/review/OS/stress/startup and unused 7200sD2.',
            'Kernel uninterruptibility, external IO and OS scheduling can exceed a bound; parent raw/wall receipts remain required.'],
        next='PARENT-NEXT.md; no automatic execution')
    save(H/'implementation-result.json',result)
    # Validate every owned JSON artifact using the requested stdlib CLI; no test rerun.
    validation=[]
    for path in sorted(H.rglob('*.json')):
        if path.name in EXCLUDED or path==H/'json-validation.json':continue
        p=subprocess.run(['python3','-m','json.tool',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        validation.append(dict(path=str(path.relative_to(H)),raw_exit=p.returncode,error=p.stderr))
    save(H/'json-validation.json',dict(method='python3 -m json.tool',files=validation,
        all_valid=all(x['raw_exit']==0 for x in validation),self_and_manifests_excluded=True))
    evidence={str(p.relative_to(H)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(H.rglob('*'))
              if p.is_file() and str(p.relative_to(H)) not in EXCLUDED}
    save(H/'evidence-manifest.json',dict(schema='r10_evidence_manifest_v1',files=evidence,
        exclusions=sorted(EXCLUDED),reason='No self digest or mutually bound manifest cycle; parent anchors both manifests externally'))
    # Check both final manifests without rewriting them or claiming runtime acceptance.
    manifest_validation=[]
    for name in sorted(EXCLUDED):
        p=subprocess.run(['python3','-m','json.tool',str(H/name)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        manifest_validation.append(dict(path=name,raw_exit=p.returncode,error=p.stderr))
    print(json.dumps(dict(status=result['status'],tests_run=None if suite is None else suite['tests_run'],
        failures=None if suite is None else suite['failures'],errors=None if suite is None else suite['errors'],
        unit_raw_exit=raw.get('raw_exit'),source_stable=all(stable.values()),base_stable=all(base_equal.values()),
        evidence_files=len(evidence),json_all_valid=all(x['raw_exit']==0 for x in validation+manifest_validation),
        manifest_validation=manifest_validation,elapsed_seconds=elapsed),sort_keys=True))
if __name__=='__main__':main()
