"""Preregistered lifecycle evidence classes; absence never implies direct reaping."""
import math
import os
from fixture_preconditions import validate_injection


def validate_fixture(receipt, events, absence, options, *, receipt_available):
    assert receipt_available and receipt, 'mandatory receipt missing'
    cls=options.get('expectation_class')
    assert cls in {'accepted','failed_supervisor_alive','failed_blocked_parent_crash',
                   'failed_with_prior_worker_reap','failed_no_child'}, 'unregistered expectation class'
    assert receipt.get('accepted') is (cls=='accepted'), 'acceptance/class differs'
    assert isinstance(receipt.get('ownership'),dict), 'explicit ownership inventory missing'
    spawns=[x for x in events if x['kind']=='owned_spawn']
    groups=receipt['ownership']
    if cls=='failed_no_child':
        assert options.get('resource_cap') is True and not spawns and groups=={}, 'pre-child ownership differs'
        assert 'inner_wait' in receipt and 'worker_wait' in receipt and receipt['inner_wait'] is None and receipt['worker_wait'] is None, 'explicit pre-child no-wait proof missing'
        assert any(x['kind']=='ownership' and x.get('ownership')=={} and x.get('owned_spawns')==[]
                   for x in events), 'explicit pre-child empty spawn/ownership witness missing'
        assert absence=={}, 'pre-child group evidence differs'
    else:
        assert spawns and set(groups)=={'supervisor','worker'}, 'positive owned inventory incomplete'
        expected={x['owned_role'] for x in spawns}
        assert set(groups)==expected==set(absence), 'positive owned inventory incomplete'
        t0=float.fromhex(receipt['t0_monotonic_hex']) if cls=='accepted' else receipt.get('executor_t0_monotonic')
        assert type(t0) in (int,float) and math.isfinite(t0), 'fixture clock missing'
        def direct(role):
            group=groups[role];pid=group['pid']
            spawn=next((x for x in spawns if x['owned_role']==role and x['pid']==pid),None)
            assert spawn is not None, 'spawn PID differs'
            report=receipt.get('inner_wait' if role=='supervisor' else 'worker_wait')
            assert report and report.get('pid')==pid and report.get('direct_child_reaped') is True, 'owned direct reap missing'
            parent=groups['supervisor']['pid'] if role=='worker' else group['parent_at_registration']
            assert type(report.get('reaped_by')) is int and report['reaped_by']==parent, 'direct wait parent differs'
            raw=report.get('raw_wait_status');at=report.get('observed_monotonic')
            assert type(raw) is int and 0<=raw<=65535 and (os.WIFEXITED(raw) or os.WIFSIGNALED(raw)), 'raw wait invalid'
            assert type(report.get('returncode')) is int and os.waitstatus_to_exitcode(raw)==report['returncode'], 'raw wait mismatch'
            assert type(at) in (int,float) and math.isfinite(at) and at>=max(t0,spawn['monotonic']), 'wait observation invalid'
            if cls=='accepted':
                cutoff=options.get('worker_seconds',8) if role=='worker' else options.get('inner_seconds',10)
                assert at<t0+cutoff and report['returncode']==options['expected_exit'], 'normal wait raw/deadline differs'
            else:
                assert at<receipt['cleanup_until_monotonic'], 'failure wait deadline differs'
            return report
        for role in expected:
            assert groups[role]['pid']==groups[role]['pgid'] and groups[role]['new_session_verified'] is True, 'ownership identity differs'
            assert groups[role]['group_absent'] is True and absence[role] is True, 'owned group survived/unproven'
        inner=direct('supervisor')
        if cls=='failed_blocked_parent_crash':
            assert options.get('mode')=='blocked' and options.get('phase')=='inner:during-worker' and options.get('mutation')=='crash', 'wrong orphan fixture'
            marker=next((x for x in events if x['kind']=='registered_worker_live_at_crash'),None)
            assert marker and marker.get('worker_pid')==groups['worker']['pid'] and marker.get('supervisor_pid')==groups['supervisor']['pid'], 'positive registered/live crash milestone missing'
            assert marker.get('registered') is True and marker.get('live_at_crash') is True and marker.get('blocked_entry') is True and marker.get('prior_worker_wait') is False, 'blocked-live/no-prior-report milestone missing'
            assert inner['returncode']==7 and inner['raw_wait_status']==7<<8, 'deliberate inner crash not observed'
            assert receipt.get('worker_wait') is None, 'fabricated wait in blocked-live crash fixture'
            assert receipt.get('reaping',{}).get('worker')=={'status':'unproven','basis':'supervisor_dead_before_report'}, 'orphan reap must stay unproven'
        else:
            direct('worker')
        if cls=='accepted':
            from long_d2_executor import validate_wait_reports
            validate_wait_reports(receipt,options['expected_exit'],options.get('outer_seconds',12))
    validate_injection(options,events,receipt)
    if options.get('mode')=='wedged':
        assert any(x['kind']=='wedged_entry' and x['role']=='worker' for x in events), 'wedged loop never entered'
    if options.get('phase')=='inner:spawn-before-registration':
        spawn=next((x for x in spawns if x['owned_role']=='worker'),None)
        assert spawn is not None, 'startup cancel did not target worker Popen'
        injection=next(x for x in events if x['kind']=='injection' and x['phase']=='spawn-before-registration')
        assert spawn['monotonic']<=injection['monotonic'], 'startup cancel preceded worker Popen'
    return True
