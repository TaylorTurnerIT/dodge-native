"""Report-only closeout after the one registered unit stage; never repairs source."""
from pathlib import Path
import datetime
import difflib
import hashlib
import json
import os
import stat
H=Path(__file__).resolve().parent
ROOT=H.parents[3]
BASE=H.parent/'postovernight-long-D2-boundary-prepare-r6'
def sha(p):
    d=hashlib.sha256()
    with p.open('rb') as f:
        for raw in iter(lambda:f.read(1024*1024),b''):d.update(raw)
    return d.hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2,allow_nan=False)+'\n')
raw=read(H/'unit-stage/raw-result.json')
suite=read(H/'unit-stage/suite-result.json') if (H/'unit-stage/suite-result.json').exists() else None
registered=read(H/'unit-stage/command.json')
source_drift={name:dict(expected=digest,actual=sha(H/name)) for name,digest in registered['source_sha256'].items() if sha(H/name)!=digest}
base=read(BASE/'parent-frozen-pins.json')
end_pins={name:dict(expected=digest,actual=sha(ROOT/name)) for name,digest in base.items()}
inputs=read(H/'input-pins.json')
authorities=[name for name in inputs['files'] if name.startswith('learning/runs/v2-orchestration/') and name.endswith('.json') and not name.endswith('/state.json')]
end_authorities={name:dict(expected=inputs['files'][name],actual=sha(ROOT/name)) for name in authorities}
save(H/'end-input-verification.json',dict(parent_pins=end_pins,authorities=end_authorities,
    all_matched=all(v['expected']==v['actual'] for v in list(end_pins.values())+list(end_authorities.values())),
    registered_source_drift=source_drift,mutable_state_excluded=True))
diffs=[];changes={}
for p in sorted(list(H.glob('*.py'))+list(H.glob('*.md'))+[H/'protocol-r6-proposal.json']):
    old=BASE/p.name
    if p.name=='protocol-r6-proposal.json':old=ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r5.json'
    before=old.read_text() if old.exists() else ''
    after=p.read_text()
    if before!=after:
        changes[p.name]=dict(before_sha256=sha(old) if old.exists() else None,after_sha256=sha(p),baseline=str(old.relative_to(ROOT)) if old.exists() else None)
        diffs.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(old.relative_to(ROOT)) if old.exists() else '/dev/null',tofile=str(p.relative_to(ROOT))))
(H/'candidate.diff').write_text(''.join(diffs))
save(H/'changes.json',dict(files=changes,scope='complete preparation-source/proposal diff; generated old envelopes are intentionally absent, not reused',original_source_fixture_copy_exact=read(H/'preparation-copy.json')['original_fixture_files']))
sourcefiles=list(H.glob('*.py'))+list(H.glob('*.md'))+[H/'protocol-r6-proposal.json']+list((H/'original-source').glob('*.py'))+list((H/'r6-source').glob('*.py'))
sources={str(p.relative_to(H)):sha(p) for p in sorted(sourcefiles)}
save(H/'source-manifest.json',dict(schema='r7_source_manifest_v1',files=sources,excludes_itself=True,
    provenance='r6-source is historical comparison only; original-source is the exact necessary fixture copy',
    registration_snapshot_source_unchanged=not source_drift,owner='released;frozen_for_parent_review',source_mode='0444',
    protocol_proposal_sha256=sha(H/'protocol-r6-proposal.json')))
ok=raw.get('raw_exit')==0 and not raw.get('timed_out') and suite is not None and suite['successful'] and not source_drift
result=dict(schema='dodge_v2_boundary_r7_implementation_result_v1',
    status='implemented_targeted_stdlib_passed_pending_parent_review_and_runtime_validation' if ok else 'implemented_validation_failed_stopped_no_patch_no_retry',
    candidate=str(H.relative_to(ROOT)),source_owner='released;frozen_for_parent_review',
    source_manifest='source-manifest.json',source_manifest_sha256=sha(H/'source-manifest.json'),
    evidence_manifest='evidence-manifest.json',complete_diff='candidate.diff',input_pins='input-pins.json',parent_next='PARENT-NEXT.md',
    base_parent_frozen_pins_verified_before_copy=8,end_input_verification='end-input-verification.json',
    changes=dict(A='retained validated direct waitpid observation descriptor in actual monitor and main before drain',
                 B='actual first_cancel_at; separate alarm/deadline competition and stable equal-time behavior',
                 C='mandatory-first immutable inner failure, guarded own-child fallback, ACK-gated same-pool reap, one send attempt, bounded outer drain and validated derived reaping status',
                 D='preregistered fixture classes and positive blocked-worker/live-registration/raw7/absence milestones; successful consumers unchanged'),
    unit=dict(stage_invocations=1,command='unit-stage/command.json',raw_result=raw,suite=suite,stdout='unit-stage/stdout.log',stderr='unit-stage/stderr.log',
              setup_precheck='unit-stage/setup-precheck.json',source_snapshot='unit-stage/sources',
              counts_are_methods=True,original_39_methods='retained; report fixtures updated for explicit class/full raw reports and stale-cache control made in-process to prohibit OS subprocess tests',
              retry=False,source_patch_after_stage=False),
    preparation=dict(max_seconds=1800,first_recorded_tool_clock_utc='2026-10-25T01:51:01Z',
                     source_registered_at_utc=registered['started_at_utc'],
                     timing_scope='recorded tool clock to source registration; no precision claim before first clock read',
                     stages=['prepare_candidate.py','finish_source.py','owned source edits; retained exact final diff'],
                     all_source_writes_owned=True,no_universal_OS_write_audit=True),
    preserved=dict(success_validate_wait_reports_and_accept_observed_byte_equal=True,
                   protected_learner_schedule_run_schedule_worker_ML_try_origin_helpers=True,
                   lifecycle_failure_pool_byte_equal=True,boundary_integrity_byte_equal=True,
                   config_sha256='2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db',
                   master_seed=5562873868232098305,D1_parent_sha256='ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f',
                   normal_seconds=dict(outer=7200,worker=7140,inner=7170),failure_rule='min(previous,earliest_failure+10,T0+7210)',
                   outer_internal_reserve_seconds=.25,inner_internal_reserve_seconds=1.,separate_RSS_MPS_limit_bytes=6442450944,
                   forced_active_B_legacy75_origins_and_full_B_R_A_endpoints=True,noncircular_DAG_external_registration_fresh_cache_prefix_B=True),
    historical_verdicts=dict(r4_units='30 passed;1 failure;8 unrun;obsolete helper-name assertion',
        r5_units='1 passed;1 setup ERROR;original-source fixture omitted',
        r6_units='39 methods passed once;historical only',
        r6_freeze_preflight='passed;historical B235/R37/A9998/119 capsule members;not current r7 proof',
        r6_OS='raw1;wall18.716s;8 cases passed;ninth direct-cancel-startup failed missing direct worker_wait;6 later unrun;both groups absent;mandatory failed receipt survived;actual worker Popen injection reached',
        r6_follow_on='no stress/startup/training followed'),
    protocol=dict(proposal='protocol-r6-proposal.json',sha256=sha(H/'protocol-r6-proposal.json'),
        canonical_future_path='learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r6.json',published=False,production_freeze_performed=False),
    limits=['Pure fake child/channel/clock and stdlib filesystem tests only; no actual waitpid, signal delivery, process-group absence, OS lifecycle, contention, startup, ML/native project import, checkpoint decode, environment, inference, gradient or training evidence.',
            'Original 39 methods and all new method/subtest counts apply only to this one registered command, not OS behavior or qualification.',
            'No claim that a final drain receives queued messages; kernel scheduling, uninterruptibility and cap truncation can leave reaping or publication unproven.',
            'First inner receipt remains immutable and may predate actual worker reap. Optional reap diagnostics are bounded best-effort only.',
            'No performance, campaign acceptance or teacher qualification claim. Parent owns fresh freeze, review reconciliation and newly registered OS/stress/startup stages before any experiment.'],
    no_auto_follow_on=True,training_launched=False,experiment_authorization_consumed_by_task=False,leases_modified=False,
    external_protocol_modified=False,original_runtime_modified=False,historical_evidence_modified=False,
    nested_delegation=False,provider_calls=False,scheduler_commit_PR_deploy_messages=False,
    finished_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
save(H/'implementation-result.json',result)
# Reporting validation only. Negative-test symlinks/FIFO are inventoried without opening them.
json_results={}
for p in sorted(H.rglob('*.json')):
    if p.is_symlink() or not stat.S_ISREG(p.lstat().st_mode) or p.name in ('json-validation.json','evidence-manifest.json'):continue
    try:json.loads(p.read_text());json_results[str(p.relative_to(H))]='parsed'
    except Exception as error:json_results[str(p.relative_to(H))]=repr(error)
save(H/'json-validation.json',dict(method='stdlib json.loads over all retained regular JSON artifacts; report-only, no candidate execution',results=json_results,
    all_parsed=all(v=='parsed' for v in json_results.values()),excludes_itself=True,evidence_manifest_generated_last=True))
files={};links={};special={}
for p in sorted(H.rglob('*')):
    name=str(p.relative_to(H));mode=p.lstat().st_mode
    if p.name=='evidence-manifest.json' and p.parent==H:continue
    if stat.S_ISREG(mode):files[name]=sha(p)
    elif stat.S_ISLNK(mode):links[name]=os.readlink(p)
    elif not stat.S_ISDIR(mode):special[name]=stat.S_IFMT(mode)
save(H/'evidence-manifest.json',dict(schema='r7_evidence_manifest_v1',files=files,symlinks=links,special_fixture_nodes=special,excludes_itself=True,
    source_manifest_included=True,old_attempts_capsules_envelopes_reused=False))
json.loads((H/'evidence-manifest.json').read_text())
for p in sourcefiles+[H/'source-manifest.json']:p.chmod(0o444)
print(json.dumps(dict(status=result['status'],tests_run=None if suite is None else suite['tests_run'],raw_exit=raw.get('raw_exit'),source_files=len(sources),evidence_files=len(files),source_drift=source_drift,source_owner=result['source_owner']),sort_keys=True))
