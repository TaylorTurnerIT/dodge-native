#!/usr/bin/env python3
"""Close preparation receipts after all redirected logs have closed. Stdlib only."""
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
R2=HERE.parent/'postovernight-long-D2-prepare-r2'


def nodes(path):
    source=path.read_text();lines=source.splitlines(True)
    return {n.name:''.join(lines[min([n.lineno]+[d.lineno for d in n.decorator_list])-1:n.end_lineno])
            for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}


def main():
    before=c.read_json(HERE/'protected-before.json')
    after={path:c.sha(path) for path in before}
    differences={path:dict(before=before[path],after=after[path]) for path in before if before[path]!=after[path]}
    c.save(HERE/'protected-after.json',after)
    c.require(not differences,'Protected immutable files changed')
    old=nodes(R2/'long_d2.py');new=nodes(HERE/'long_d2.py')
    names=('Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control',
           'tree_fingerprint','assert_equal_tree','validate_long_config','expected_lease','assert_lease',
           'check_module_origins','outcome_fields','result_code')
    equal={name:old[name]==new[name] for name in names}
    c.require(all(equal.values()),'Protected ML/validator node differs')
    c.save(HERE/'source-equality.json',dict(byte_equal_nodes=equal,worker_whole_body_equal=False,
        worker_exception_authority='required parent addendum PLAN-WORKER-FAILURE',
        worker_change_scope='supervision-only failure timestamp/ACK, shared persistence deadline, no ordinary verification after failure; ML operations unchanged'))
    (HERE/'worker-hook.diff').write_text(''.join(difflib.unified_diff(old['worker'].splitlines(True),new['worker'].splitlines(True),
            fromfile='frozen-r2/worker',tofile='r3/worker')))
    patch=[]
    for path in sorted(HERE.iterdir()):
        if path.is_file() and path.suffix in ('.py','.txt','.md'):
            previous=R2/path.name
            patch.extend(difflib.unified_diff(previous.read_text().splitlines(True) if previous.exists() else [],
                path.read_text().splitlines(True),fromfile='frozen-r2/'+path.name if previous.exists() else '/dev/null',
                tofile='r3/'+path.name))
    (HERE/'full-r2-diff.patch').write_text(''.join(patch))
    sources={p.name:c.sha(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.suffix in ('.py','.txt','.md')}
    c.save(HERE/'source-manifest.json',sources)
    mutable={}
    for path,prior in c.read_json(HERE/'parent-mutable-before.json').items():
        mutable[path]=dict(before_sha256=prior['sha256'],after_sha256=c.sha(path),
                           changed=prior['sha256']!=c.sha(path),text=Path(path).read_text())
    c.save(HERE/'parent-mutable-after.json',mutable)
    matrix=c.read_json(HERE/'attempts/matrix-final/summary.json')
    units=c.read_json(HERE/'attempts/units-final-r2/unit-result.json')
    c.require(units['successful'] and units['ML_imports'] is False,'Final unit controls failed')
    inventory=c.read_json(HERE/'expanded-inventory.json');freeze=c.read_json(HERE/'freeze-receipt.json')
    c.require(inventory['all_old_exact_digests_retained'] and inventory['retained_old_union_count']==793,'Retained pin union differs')
    final_source_hashes=c.read_json(HERE/'attempts/matrix-final/tested-sources.json')
    changed_since_matrix={name:dict(tested=digest,current=c.sha(HERE/name)) for name,digest in final_source_hashes.items()
                          if c.sha(HERE/name)!=digest}
    runtime={'long_d2.py','long_d2_executor.py','lifecycle.py','processes.py','synthetic.py','run_checks.py'}
    c.require(not runtime.intersection(changed_since_matrix),'Execution source changed since final matrix')
    c.require(all(c.sha(HERE/name)==digest for name,digest in units['sources'].items()),'Source changed since final unit controls')
    # Independent current absence checks, without claiming nonchild waitpid reaping.
    group_ids=set()
    for result in matrix['results']:
        root=Path(result['argv'][-1]);receipt=root/'execution/acceptance-receipt.json'
        if receipt.exists():
            for record in c.read_json(receipt).get('ownership',{}).values():group_ids.add(record['pgid'])
    absence={str(pgid):owned.absent(pgid,time.monotonic()+.2) for pgid in sorted(group_ids)}
    c.require(all(absence.values()),'Owned synthetic group still present')
    c.save(HERE/'owned-groups-final.json',dict(groups=absence,nonchild_worker_waitpid_claimed=False))
    review=ROOT/'learning/runs/v2/postovernight-long-D2-supervisor-review-r2'
    negative=[]
    for name in ('findings.json','delayed-unmask-summary.json','independent-probe-summary.json','independent-contract-assertions.log',
                 'probe_final_unmask.py','old-boundary-summary.json'):
        path=review/name
        c.require(before.get(str(path))==c.sha(path),'Retained negative evidence changed')
        negative.append(dict(path=str(path),sha256=c.sha(path),new_execution=False))
    c.save(HERE/'negative-controls.json',dict(retained_exact_r2=negative,
        actual_r2_fresh_executions=0,assertion_failures_not_API_errors=True,old_raw_minus14_cause='unproven',
        old_minus14_retried=False,historical_pass_counts_transferred=False))
    commands=[]
    for log in sorted((HERE/'attempts').glob('*.log')):
        commands.append(dict(log=str(log.relative_to(HERE)),sha256=c.sha(log)))
    result=dict(version='long_D2_r3_preparation_result_v1',status='prepared_for_fresh_frozen_review_only',
        production_launch_performed=False,active_lease_created=False,campaign_output_created=False,
        execution_directory_created=False,training_inference_teacher_load_gameplay=False,children_delegated=False,
        installs_external_messages_commits_PR_deploy=False,
        protocol_sha256=c.PROTOCOL_SHA256,config_sha256=c.CONFIG_SHA256,
        controller_sha256=c.sha(HERE/'long_d2.py'),executor_sha256=c.sha(HERE/'long_d2_executor.py'),
        identity_raw_sha256=inventory['identity_raw_sha256'],identity_semantic_sha256=inventory['identity_semantic_sha256'],
        capsule_manifest_sha256=inventory['capsule_manifest_sha256'],capsule_readonly=True,
        retained_old_pin_union=793,expanded_full_pin_count=inventory['new_full_pin_count'],legacy_sources=75,
        protected_before_after_count=len(before),protected_mismatches=differences,
        mutable_parent_snapshots_separate=True,source_equality=equal,worker_hook_diff='worker-hook.diff',
        full_diff='full-r2-diff.patch',current_unit_methods=units['methods_run'],
        current_full_lifecycle_OS_subprocesses=matrix['OS_subprocesses'],
        method_and_subprocess_counts_not_added=True,current_owned_groups_positively_absent=len(absence),
        additional_test_source_changes_after_matrix=changed_since_matrix,
        additional_test_source_verified_by_final_unit_run=True,
        final_matrix='attempts/matrix-final/summary.json',unit_receipt='attempts/units-final-r2/unit-result.json',
        exact_invocation='invocation.json',external_registration='registration.json',required_15_field_lease='required-lease.json',
        pure_stdlib_preflight='pure-executor-preflight.json',hash_volume_control='hash-volume-receipt.json',
        attempts_and_logs=commands,failed_attempts_and_per_case_receipts_retained=True,
        aggregate_stdout_log_loss='attempts/aggregate-log-note.json',all_aggregate_stdout_logs_retained=False,
        actual_final_commands=[
            [str(ROOT/'learning/.venv/bin/python'),'-B',str(HERE/'run_checks.py'),str(HERE/'attempts/matrix-final')],
            [str(ROOT/'learning/.venv/bin/python'),'-B',str(HERE/'run_unit_checks.py'),str(HERE/'attempts/units-final-r2')],
            [str(ROOT/'learning/.venv/bin/python'),'-B',str(HERE/'freeze.py')],
            [str(ROOT/'learning/.venv/bin/python'),'-B',str(HERE/'volume_probe.py')]],
        limitations=['Fresh frozen independent review remains required before any production lease or experiment.',
            'One intermediate aggregate stdout log was overwritten by a failed directory-exists attempt; per-case raw/wall/events/commands/source snapshots and summary remain retained.',
            'Direct legitimate post-scan signals and changes after the final finite filesystem read may remain unobserved.',
            'Post-scan direct-signal controls intentionally retain provisional exit2 and expose the observation limit.',
            'Recorded forwarded cancellation, persistent observed input/lease mutations, raw failures and late walls reject.',
            'Old unexplained raw -14 cause remains unproven and was not identically retried.',
            'Kernel scheduling/uninterruptible IO can prevent bounds; missing or late raw/wall/absence proof is failure.',
            'No actual model/Adam/RNG restoration, entry equality, MPS/native resource behavior or learning was tested.',
            'Hash-volume controls do not guarantee future artifact volume or ML timing.'])
    c.save(HERE/'implementation-result.json',result)
    # No redirected log writer is open at this point. This inventory excludes only itself.
    artifacts={str(p.relative_to(HERE)):c.sha(p) for p in sorted(HERE.rglob('*'))
               if p.is_file() and p!=HERE/'artifact-inventory.json'}
    c.save(HERE/'artifact-inventory.json',artifacts)
    print(json.dumps({k:result[k] for k in ('status','current_unit_methods','current_full_lifecycle_OS_subprocesses',
        'expanded_full_pin_count','protected_before_after_count','current_owned_groups_positively_absent')},sort_keys=True))


if __name__=='__main__':main()
