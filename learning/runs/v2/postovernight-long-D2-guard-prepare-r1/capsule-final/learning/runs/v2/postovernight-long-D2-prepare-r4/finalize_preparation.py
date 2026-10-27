"""Close evidence after all redirected logs have closed; no candidate launch."""
from pathlib import Path
import ast
import difflib
import json
import os
import subprocess
import sys
import time
import long_d2 as c
import processes as owned
HERE=Path(__file__).resolve().parent
ROOT=c.ORIGINAL_ROOT
R3=HERE.parent/'postovernight-long-D2-prepare-r3'

def nodes(path):
    source=path.read_text();lines=source.splitlines(True)
    return {n.name:''.join(lines[min([n.lineno]+[d.lineno for d in n.decorator_list])-1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}

def main():
    before=c.read_json(HERE/'protected-before.json');after={p:c.sha(p) for p in before}
    changes={p:dict(before=before[p],after=after[p]) for p in before if before[p]!=after[p]}
    c.save(HERE/'protected-after.json',after);c.require(not changes,'Protected immutable inputs changed')
    mutable={}
    for path,old in c.read_json(HERE/'parent-mutable-before.json').items():
        mutable[path]=dict(before_sha256=old['sha256'],after_sha256=c.sha(path),changed=old['sha256']!=c.sha(path),text=Path(path).read_text(),ownership='parent bookkeeping; never written by R4 preparation')
    c.save(HERE/'parent-mutable-after.json',mutable)
    old=nodes(R3/'long_d2.py');new=nodes(HERE/'long_d2.py')
    protected=('Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control','tree_fingerprint','assert_equal_tree','validate_long_config','expected_lease','assert_lease','check_module_origins','outcome_fields','result_code')
    equal={name:old[name]==new[name] for name in protected};c.require(all(equal.values()),'Protected source node changed')
    c.save(HERE/'source-equality.json',dict(byte_equal_nodes=equal,worker_ML_try_body='byte equality tested in final current source unit method',worker_change_scope='only supervision hooks, ACK/write permission and worker failure CLI close',whole_worker_equal=False))
    with (HERE/'worker-hook.diff').open('x') as out:
        for name in ('worker_failure','worker_write_permission','worker','main'):
            out.write(''.join(difflib.unified_diff(old.get(name,'').splitlines(True),new[name].splitlines(True),fromfile='r3/'+name,tofile='r4/'+name)))
    with (HERE/'full-r3-diff.patch').open('x') as out:
        for p in sorted(HERE.iterdir()):
            if p.is_file() and p.suffix in ('.py','.txt','.md'):
                previous=R3/p.name
                out.write(''.join(difflib.unified_diff(previous.read_text().splitlines(True) if previous.exists() else [],p.read_text().splitlines(True),fromfile='r3/'+p.name if previous.exists() else '/dev/null',tofile='r4/'+p.name)))
    sources={p.name:c.sha(p) for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.txt','.md')}
    c.save(HERE/'source-manifest.json',sources)
    units=c.read_json(HERE/'attempts/units-final/unit-result.json');c.require(units['successful'] and not units['ML_imports'],'Final units failed')
    c.require(all(c.sha(HERE/n)==v for n,v in units['sources'].items()),'Source changed after final unit receipt')
    matrix=c.read_json(HERE/'attempts/matrix-final/summary.json');tested=c.read_json(HERE/'attempts/matrix-final/tested-sources.json')
    drift={n:dict(tested=v,current=c.sha(HERE/n)) for n,v in tested.items() if c.sha(HERE/n)!=v}
    c.require(not drift,'Existing source changed after final matrix')
    additions={n:v for n,v in sources.items() if n.endswith('.py') and n not in tested}
    c.require(set(additions)<= {'prepare_checks.py','finalize_preparation.py'},'New source lacks actual matrix scope proof')
    controls={'matrix-final':matrix}
    if (HERE/'attempts/matrix-01/summary.json').exists():controls['matrix-01']=c.read_json(HERE/'attempts/matrix-01/summary.json')
    groups=set();case_count=0;read_events=[]
    for label,control in controls.items():
        for row in control['results']:
            case_count+=1;root=Path(row['argv'][-1])
            receipt=root/'execution/acceptance-receipt.json'
            if receipt.exists():groups.update(r['pgid'] for r in c.read_json(receipt).get('ownership',{}).values())
            for event_path in root.glob('*-events.jsonl'):
                for line in event_path.read_text().splitlines():
                    event=json.loads(line)
                    if event['kind']=='ownership':groups.update(r['pgid'] for r in event['ownership'].values())
                    if label=='matrix-final' and event['kind']=='final_IO_boundary':read_events.append(event)
            c.require(row['raw_wait']['returncode']==row['expected'] and not row['harness_kill_required'],'Invalid OS receipt')
            c.require(row['elapsed_seconds']<=row['maximum_wall_seconds'],'OS wall exceeds normal plus one cleanup pool')
    absence={str(g):owned.absent(g,time.monotonic()+.2) for g in sorted(groups)};c.require(all(absence.values()),'Owned OS group survives')
    c.save(HERE/'owned-groups-final.json',dict(groups=absence,nonchild_waitpid_claimed=False,all_direct_executors_reaped=True))
    c.require(read_events and all(e['latch_phase']=='NORMAL' and not e['watchdog_alive'] and not any(e['guard_handles_alive']) for e in read_events),'Final IO seam lacks interrupting owner/teardown proof')
    pins=c.read_json(HERE/'expanded-inventory.json');c.require(pins['retained_old_union_count']==9675 and pins['all_old_exact_digests_retained'],'Retained union differs')
    registration=c.read_json(HERE/'registration.json');lease=c.read_json(HERE/'required-lease.json')
    c.require(len(lease)==15 and set(lease)==c.LEASE_KEYS,'Lease schema differs')
    p3=c.read_json(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol-r3.json');p4=c.registered_protocol(ROOT/c.PROTOCOL_REL)
    expected=dict(p3);expected['controller']=p4['controller'];expected['registered_at_utc']=p4['registered_at_utc'];expected['terminal_lifecycle']=dict(p3['terminal_lifecycle'],executor=p4['terminal_lifecycle']['executor'])
    c.require(expected==p4,'Protocol changed outside three registered fields')
    c.require(not (ROOT/p4['output']).exists() and not (ROOT/Path(p4['terminal_lifecycle']['acceptance_receipt']).parent).exists(),'Production output exists')
    c.require(c.read_json(c.STATE_PATH).get('active_long_campaign') is None,'Production lease exists')
    evidence=c.read_json(HERE/'governing-read-receipt.json')['files'];c.verify_files(evidence)
    c.save(HERE/'negative-controls.json',dict(retained_R3={p:d for p,d in evidence.items() if 'review-r3/' in p or 'api-audit-r1/' in p},fresh_old_subprocesses=0,old_R3_blocked_final_IO_raw=-9,old_harness_kill_required=True,old_acceptance=False,old_missing_ACK_assertion_failed=True,no_API_import_error_credit=True,old_R2_minus14_cause='unproven; not retried',old_R3_intermediate_aggregate_stdout='unrecoverable; retained limitation unchanged'))
    final=dict(version='long_D2_r4_preparation_result_v1',status='prepared_for_fresh_frozen_review_only',fixed_blockers=['SUP-001-R3','WORKER-ACK-001'],
        production_launch_performed=False,active_lease_created=False,campaign_output_created=False,execution_directory_created=False,ML_native_import_load_inference_gradient_gameplay_training=False,children_installs_external_messages_commits_PR_deploy=False,
        protocol_path=c.PROTOCOL_REL,protocol_sha256=c.PROTOCOL_SHA256,protocol_version=p4['version'],lifecycle_schema=p4['terminal_lifecycle']['schema'],config_sha256=c.CONFIG_SHA256,
        controller_sha256=c.sha(HERE/'long_d2.py'),executor_sha256=c.sha(HERE/'long_d2_executor.py'),identity_raw_sha256=pins['identity_raw_sha256'],identity_semantic_sha256=pins['identity_semantic_sha256'],capsule_manifest_sha256=registration['capsule_manifest_sha256'],capsule_readonly=True,
        old_full_pins_retained=9675,expanded_full_pin_count=pins['new_full_pin_count'],legacy_sources=75,protected_before_after_count=len(before),protected_mismatches=changes,parent_mutable_changes_separate=mutable and 'parent-mutable-after.json',source_equal_nodes=equal,
        current_unit_methods=units['methods_run'],unit_latch_OS_subprocesses=6,worker_native_AST_scenarios=len(list((HERE/'attempts/units-final').glob('worker-*.json'))),final_full_lifecycle_OS_subprocesses=matrix['OS_subprocesses'],total_fresh_full_lifecycle_OS_subprocesses=case_count,counts_are_distinct_not_added=True,owned_groups_positively_absent=len(absence),
        final_matrix='attempts/matrix-final/summary.json',unit_receipt='attempts/units-final/unit-result.json',new_sources_after_matrix_snapshot=additions,source_drift_after_matrix=drift,
        actual_scope_proof={'runtime_fixture_OS_driver':'exact final matrix tested-sources + source snapshots','worker_hooks':'actual source AST except/finally and tail; fake ML body and IO callbacks; real notify_failure ACK validation','freeze.py':'executed by prepare_checks.py; readonly pure preflight verifies new capsule','volume_probe.py':'executed stdlib volume timing','prepare_checks.py':'actual command receipt and final preparation-checks.json','finalize_preparation.py':'executed current source, checked receipts, JSON and final inventory; no OS behavior claim','source_manifest':'observed hashes, not blanket behavior coverage'},
        exact_invocation='invocation.json',external_registration='registration.json',required_15_field_lease='required-lease.json',pure_preflight='pure-executor-preflight.json',hash_volume='hash-volume-receipt.json',full_diff='full-r3-diff.patch',worker_hook_diff='worker-hook.diff',aggregate_log_overwrites=False,
        limitations=['Fresh frozen review and separate parent acceptance required before launch.','No actual ML/native/Torch import, checkpoint load, restoration, entry equality, runtime resource qualification or training.','Finite post-scan signals and transient filesystem observation limits remain.','Kernel uninterruptibility/OS scheduling are not bounded guarantees; missing raw/wall/absence reject.','Historical R3 lost aggregate stdout remains unrecoverable; no old pass count transfers.','Stdlib volume timing does not guarantee future campaign artifact size or performance.'])
    c.save(HERE/'implementation-result.json',final)
    for path in HERE.glob('*.json'):json.loads(path.read_text())
    subprocess.run([sys.executable,'-B','-m','json.tool',str(HERE/'implementation-result.json')],check=True,stdout=subprocess.DEVNULL)
    # All redirected log writers have returned and closed before this inventory.
    artifacts={str(p.relative_to(HERE)):c.sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p!=HERE/'artifact-inventory.json'}
    c.save(HERE/'artifact-inventory.json',artifacts)
    c.verify_files({str(HERE/p):v for p,v in artifacts.items()})
    print(json.dumps({k:final[k] for k in ('status','current_unit_methods','final_full_lifecycle_OS_subprocesses','total_fresh_full_lifecycle_OS_subprocesses','expanded_full_pin_count','protected_before_after_count','owned_groups_positively_absent')},sort_keys=True))

if __name__=='__main__':main()
