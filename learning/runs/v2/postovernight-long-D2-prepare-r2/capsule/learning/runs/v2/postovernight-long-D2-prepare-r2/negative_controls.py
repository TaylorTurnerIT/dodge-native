#!/usr/bin/env python3
"""Retain deliberate broken helper copies and require assertion failures.

Each case runs a discriminating test against the exact copied file, using only
stdlib synthetic fixtures. Import/API errors do not count as a killed mutant.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import long_d2 as c
HERE=Path(__file__).resolve().parent
CASES=[
 ('config_exactness',"canonical(config) == canonical(protocol['config'])",'True',
  'ConfigTests.test_every_config_leaf_mutation'),
 ('lease_binding','canonical(lease) == canonical(expected)','True',
  'LeaseTests.test_each_lease_field_tamper'),
 ('module_mirror',"sha(path) == pin['sha256'] == sha(capsule_root / pin['mirror'])",'True',
  'IdentityTests.test_module_origins_and_mirrors'),
 ('state_equality','require(a == b, label','require(True, label',
  'StateTests.test_bitwise_model_adam_rng_changes'),
 ('entry_rows','canonical(actual) == canonical(expected)','True',
  'StateTests.test_control_all_fields_and_completion_order'),
 ('block_admission','if remaining() < schedule.block_cost():','if False:',
  'ScheduleTests.test_budget_closure_not_pass'),
 ('reserve_growth','self.U = max(self.U, 1.25 * wall)','self.U = 25.0',
  'ScheduleTests.test_periodic_checkpoint_in_update_bound'),
 ('closure_exit2','        return 2\n    return 1','        return 0\n    return 1',
  'FinalizationTests.test_budgetclosure_exit2_bindings'),
 ('KL_safety',"require(self.kl_count < 3,'Approximate KL", "require(True,'Approximate KL",
  'LearnerTests.test_KL_three_consecutive_and_reset'),
 ('partial_steps',"partial = progress.get('optimizer_steps',0) if progress.get('in_update',False) else 0",'partial = 0',
  'StateTests.test_inherited_phase_and_partial_optimizer_accounting'),
 ('stable_manifest',"require(stable,'Owned leader/group absence unproven; artifacts were not hashed','publication_failure')",'pass',
  'FinalizationTests.test_unproven_owned_group_blocks_all_hashes'),
 ('deadline_after_write',"require(clock()<deadline,'7200s deadline reached during '+stage,'wall_guard')",'pass',
  'FinalizationTests.test_late_write_and_hash_revoke_success'),
 ('deferred_cancel','if cancel.cancellation_requests:', 'if False:',
  'SupervisorTests.test_signal_latched_through_cleanup_close_verify_streamclose'),
 ('resource_guard',"require(max(rss,peak) <= LIMIT and mps <= LIMIT, 'RSS or MPS resource limit exceeded', 'resource_stop')",'pass',
  'GuardTests.test_mps_limit_separate_from_rss'),
]


def main():
    round_name=sys.argv[1] if len(sys.argv)>1 else 'r1'
    c.require(round_name.isalnum(),'Invalid receipt round')
    original=(HERE/'long_d2.py').read_text()
    directory=HERE/('negative-controls-source-'+round_name);directory.mkdir(exist_ok=False)
    results=[]
    for name,before,after,test in CASES:
        count=original.count(before)
        # The cancellation mutation removes every relevant latch read, preserving
        # handler behavior so the tests reach their outcome assertions.
        c.require(count>=1,'Mutation target missing: '+name)
        changed=original.replace(before,after)
        compile(changed,name,'exec')
        target=directory/(name+'.py');target.write_text(changed)
        command=[sys.executable,'-B','-m','unittest','test_long_d2.'+test,'-v']
        result=subprocess.run(command,cwd=HERE,capture_output=True,text=True,timeout=45,
                env=dict(os.environ,LONG_D2_TEST_SOURCE=str(target),PYTHONDONTWRITEBYTECODE='1'))
        log=HERE/('negative-'+round_name+'-'+name+'.log');log.write_text(result.stdout+result.stderr)
        assertion_failure=result.returncode!=0 and 'FAIL:' in result.stderr and 'AssertionError' in result.stderr
        api_error='ERROR:' in result.stderr or 'ImportError' in result.stderr or 'SyntaxError' in result.stderr
        entry=dict(name=name,test=test,command=command,source=str(target.relative_to(HERE)),
                   source_sha256=c.sha(target),log=str(log.relative_to(HERE)),log_sha256=c.sha(log),
                   replacements=count,exit_code=result.returncode,assertion_failure=assertion_failure,
                   API_or_import_errors=api_error,killed=assertion_failure and not api_error,
                   original_fragment=before,broken_fragment=after)
        results.append(entry)
        print(name,'killed' if entry['killed'] else 'NOT KILLED',flush=True)
    receipt=dict(version='long_D2_negative_controls_v1',base_controller_sha256=c.sha(HERE/'long_d2.py'),
                 count=len(results),all_killed=all(x['killed'] for x in results),cases=results,
                 no_project_torch_native_imports=True)
    c.save(HERE/('negative-control-receipt-'+round_name+'.json'),receipt)
    return 0 if receipt['all_killed'] else 1

if __name__=='__main__':raise SystemExit(main())
