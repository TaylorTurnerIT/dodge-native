"""Positive lifecycle fixture milestones. Empty dictionaries are not witnesses."""
def validate_fixture(receipt, events, absence, options, *, receipt_available):
    assert receipt_available and receipt, 'mandatory receipt missing'
    assert isinstance(receipt.get('ownership'),dict), 'explicit ownership inventory missing'
    spawns=[x for x in events if x['kind']=='owned_spawn']
    groups=receipt['ownership']
    if not spawns:
        assert not groups, 'owned group without spawn witness'
        assert options.get('resource_cap') is True, 'unregistered premature pre-child exit'
        assert any(x['kind']=='ownership' and x.get('ownership')=={} and x.get('owned_spawns')==[]
                   for x in events), 'explicit pre-child empty spawn/ownership witness missing'
        assert absence=={}, 'pre-child group evidence differs'
    else:
        expected={x['owned_role'] for x in spawns}
        assert set(groups)==expected==set(absence), 'positive owned inventory incomplete'
        for role in expected:
            pid=groups[role]['pid']
            assert any(x['owned_role']==role and x['pid']==pid for x in spawns), 'spawn PID differs'
            assert absence[role] is True, 'owned group survived/unproven'
            key='inner_wait' if role=='supervisor' else 'worker_wait'
            report=receipt.get(key)
            assert report and report.get('pid')==pid and report.get('direct_child_reaped') is True, 'owned direct reap missing'
    if options.get('phase'):
        assert any(x['kind']=='injection' and x['role']+':'+x['phase']==options['phase'] for x in events), 'requested injection missed'
    if options.get('mode')=='wedged':
        assert any(x['kind']=='wedged_entry' and x['role']=='worker' for x in events), 'wedged loop never entered'
    if options.get('phase')=='inner:spawn-before-registration':
        spawn=next((x for x in spawns if x['owned_role']=='worker'),None)
        assert spawn is not None, 'startup cancel did not target worker Popen'
        injection=next(x for x in events if x['kind']=='injection' and x['phase']=='spawn-before-registration')
        assert spawn['monotonic']<=injection['monotonic'], 'startup cancel preceded worker Popen'
    return True
