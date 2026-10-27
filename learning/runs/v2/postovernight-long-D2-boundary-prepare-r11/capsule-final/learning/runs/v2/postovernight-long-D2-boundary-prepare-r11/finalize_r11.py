"""Close evidence once without executing or modifying candidate source/tests."""
from pathlib import Path
import ast,datetime,difflib,hashlib,json,os,subprocess,time
H=Path(__file__).resolve().parent;ROOT=H.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,value):(H/name).write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')
def files(paths):return {str(p.relative_to(H)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(paths) if p.is_file()}
def main():
    raw=json.loads((H/'unit-stage/raw-result.json').read_text())
    suite=json.loads((H/'unit-stage/suite-result.json').read_text()) if (H/'unit-stage/suite-result.json').exists() else None
    inputs=json.loads((H/'input-pins.json').read_text());checks={}
    for path,digest in {**inputs['parent_frozen_pins'],**inputs['authorities']}.items():checks[path]=sha(ROOT/path)==digest
    sources=list(H.glob('*.py'))+list(H.glob('*.md'))+[H/'protocol-r8-proposal.json']
    # Candidate source is immutable after validation, including scripts and handoff.
    command=json.loads((H/'unit-stage/command.json').read_text())
    stage_equal={p.name:sha(p)==command['source_sha256'][p.name] for p in H.glob('*.py')}
    stage_equal['PARENT-NEXT.md']=(H/'PARENT-NEXT.md').read_bytes()==(H/'unit-stage/sources/PARENT-NEXT.md').read_bytes()
    stage_equal['protocol-r8-proposal.json']=(H/'protocol-r8-proposal.json').read_bytes()==(H/'unit-stage/sources/protocol-r8-proposal.json').read_bytes()
    diffs=[];changed=[]
    for p in sorted(sources):
        before=H/'r10-source'/p.name
        if p.name=='protocol-r8-proposal.json':before=H/'r10-source/protocol-r7-proposal.json'
        a=before.read_text() if before.exists() else '';b=p.read_text()
        if a!=b:
            changed.append(p.name);diffs.extend(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='r10/'+before.name if before.exists() else '/dev/null',tofile='r11/'+p.name))
    (H/'candidate.diff').write_text(''.join(diffs))
    external_before=(H/'workspace-before.txt').read_text().splitlines()
    external_after=subprocess.check_output(['git','status','--porcelain=v1'],cwd=ROOT,text=True).splitlines()
    save('end-verification.json',dict(frozen_pins_and_authorities=checks,source_stage_bytes_equal=stage_equal,
        all_pins_match=all(checks.values()),all_stage_source_equal=all(stage_equal.values()),
        git_status_changed_lines=sorted(set(external_after)^set(external_before)),
        git_status_limit='Untracked ignored run paths may not appear; hashes verify exact frozen inputs. No universal write attestation.',
        temporary_bootstrap_path_absent=not Path('/tmp/dodge-r11-bootstrap.py').exists()))
    passed=bool(suite and suite['successful'] and raw.get('raw_exit')==0 and not raw.get('timed_out'))
    end=datetime.datetime.now(datetime.timezone.utc);start=datetime.datetime.fromisoformat(inputs['started_at_utc'])
    elapsed=(end-start).total_seconds()
    save('implementation-result.json',dict(schema='distinct_dodge_v2_r11_implementation_result_v1',
        status='source_prepared_one_stdlib_stage_passed' if passed else 'stopped_on_first_unexpected_validation_failure',
        candidate=str(H.relative_to(ROOT)),repairs=['qualified_staged_owned_escalation','per_endpoint_IPC_error_isolation'],
        unit_raw=raw,unit_summary=None if suite is None else {k:v for k,v in suite.items() if k not in ('planned_tests','unrun_tests')},
        prior_91_methods_planned=True,prior_counts_transferred=False,
        source_changes=changed,source_ownership='released;source_bytes_frozen_for_parent_review;no_auto_followon',
        protocol_proposal=dict(path='protocol-r8-proposal.json',sha256=sha(H/'protocol-r8-proposal.json'),canonical_future_external_path='learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r8.json',published=False),
        budget=dict(preparation_max_seconds=1800,started_at_utc=inputs['started_at_utc'],finished_at_utc=end.isoformat(),elapsed_seconds=elapsed,within_preparation_budget=elapsed<=1800,stdlib_max_seconds=300,one_stage=True),
        invariant_pins_match=all(checks.values()),source_bytes_equal_stage=all(stage_equal.values()),
        success_consumers='Exact r10 bytes; controller functions/classes, worker ML body, transport/lifecycle/processes/boundary_integrity and all 15 fixtures unchanged.',
        protected=dict(config_sha256='2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db',seed=5562873868232098305,D1_sha256='ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f'),
        limits=['Fake process/clock/channel/readiness and real source only; no OS closure or transport-cause proof.',
          'Inner reap sleep expressions become generator yields in the single-threaded model; remainder is extracted actual source.',
          'Historical r10 raw1/wall30.620216/13 cases and Sonnet18 model assertions do not transfer.',
          'One /tmp bootstrap write-location deviation is disclosed in scope-deviation.json; task-created temporary path moved into owned output.',
          'No new OS/lifecycle/probe/stress/startup, ML/native imports/checkpoint decode/env/inference/gradient/training, lease, scheduler, commit/PR/deploy/messages or nested delegation.',
          'Parent owns reconciliation, exact external protocol, fresh freeze/runtime/review and one still-unused 7200s D2.'],
        failures=[] if passed else [dict(raw=raw,failed_tests=None if suite is None else suite['failed_tests'],error_tests=None if suite is None else suite['error_tests'])],
        no_post_failure_patch=True,no_retry=True,no_auto_followon=True,production_freeze=False,training_launched=False,authorization_consumed=False))
    # json.tool is the requested syntax receipt, not another candidate test stage.
    paths=[p for p in H.rglob('*.json') if p.name not in ('json-validation.json','source-manifest.json','evidence-manifest.json')]
    validations={};cache=H/'json-check-pycache';cache.mkdir()
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(cache))
    for p in sorted(paths):
        argv=['learning/.venv/bin/python','-B','-m','json.tool',str(p)]
        result=subprocess.run(argv,cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=10)
        validations[str(p.relative_to(H))]=dict(raw_exit=result.returncode,sha256=sha(p),error=result.stderr)
        if result.returncode:break
    save('json-validation.json',dict(command_template=['learning/.venv/bin/python','-B','-m','json.tool','<exact owned JSON path>'],files=validations,all_valid=len(validations)==len(paths) and all(v['raw_exit']==0 for v in validations.values()),cache_empty=not any(cache.iterdir())))
    source_paths=sources+[p for name in ('original-source','r6-source','r9-source','r10-source') for p in (H/name).rglob('*') if p.is_file()]
    source_paths += [H/name for name in ('preparation-copy.json','retained-r9-injection.json','protocol-r7-proposal.json')]
    save('source-manifest.json',dict(schema='r11_source_manifest_v1',files=files(source_paths),self_excluded=True,production_freeze=False))
    save('evidence-manifest.json',dict(schema='r11_evidence_manifest_v1',files=files(p for p in H.rglob('*') if p.is_file() and p.name!='evidence-manifest.json'),self_excluded=True,source_manifest_is_one_way_leaf=True))
    # Manifest JSONs validated after emission without changing their hashed leaves.
    for name in ('source-manifest.json','evidence-manifest.json','json-validation.json'):
        result=subprocess.run(['learning/.venv/bin/python','-B','-m','json.tool',str(H/name)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=10)
        print(name,'json.tool raw_exit',result.returncode)
        if result.returncode:print(result.stderr);return 1
    print(json.dumps(dict(status='passed' if passed else 'validation_failed_no_retry',methods=None if suite is None else suite['tests_run'],preparation_seconds=elapsed,source_files=len(source_paths),pins_match=all(checks.values()),stage_source_equal=all(stage_equal.values())),sort_keys=True))
    return 0
if __name__=='__main__':raise SystemExit(main())
