"""Independent scenario registration and positive pre-mutation entry witnesses."""

# These phases follow the actual calls: inner pending_once runs after ACTIVE()
# changes NORMAL to DEFER. Outer receipt hooks run before any such deferral.
PHASES={
    'outer:receipt-before':('NORMAL',('outer_gate_ack_sent','worker_handshake_complete',
        'worker_direct_wait_observed','worker_wait_sent','inner_ready_sent',
        'inner_direct_wait_observed','normal_accepted_publication_prepared')),
    'outer:receipt-after':('NORMAL',('outer_gate_ack_sent','worker_handshake_complete',
        'worker_direct_wait_observed','worker_wait_sent','inner_ready_sent',
        'inner_direct_wait_observed','normal_accepted_publication_prepared','normal_accepted_publication')),
    'inner:terminal-after':('NORMAL',('worker_spawned','registration_ack_received',
        'worker_handshake_complete','worker_direct_wait_observed','worker_wait_sent','normal_terminal_publication')),
    'inner:pending-before':('DEFER',('worker_spawned','registration_ack_received',
        'worker_handshake_complete','worker_direct_wait_observed','worker_wait_sent',
        'normal_terminal_publication','inner_ready_sent')),
    'inner:spawn-before-registration':('NORMAL',('worker_spawned',)),
    'inner:during-worker':('NORMAL',('worker_spawned','registration_ack_received',)),
}


def preregister(options):
    """Called before launch or any receipt; never derive a class from outcomes."""
    options=dict(options)
    phase=options.get('phase')
    if phase:
        assert phase in PHASES, 'unregistered injection phase'
        expected,positive=PHASES[phase]
        if options.get('expectation_class')=='failed_blocked_parent_crash':
            positive=positive+('registered_worker_live_at_crash',)
        options['injection_contract']=dict(expected_latch_phase=expected,
            positive_prerequisites=list(positive),reject_prior_global_failure=True,
            failure_attribution='post_injection_first_observation_only;not_exclusive_causality')
    else:
        options['injection_contract']=None
    return options


def check_precondition(options, snapshot):
    contract=options.get('injection_contract')
    assert isinstance(contract,dict), 'fixture_precondition_failed: missing preregistration'
    expected=preregister({k:v for k,v in options.items() if k!='injection_contract'})['injection_contract']
    assert contract==expected, 'fixture_precondition_failed: contract differs from scenario'
    assert snapshot.get('latch_phase')==contract['expected_latch_phase'], 'fixture_precondition_failed: wrong latch phase'
    assert snapshot.get('pool_first') is None and snapshot.get('pool_until') is None and snapshot.get('first_global_failure') is None, 'fixture_precondition_failed: earlier global failure'
    milestones=snapshot.get('milestones')
    assert isinstance(milestones,dict) and contract['positive_prerequisites'], 'fixture_precondition_failed: missing positive inventory'
    for name in contract['positive_prerequisites']:
        assert milestones.get(name) is True, 'fixture_precondition_failed: missing '+name
    assert snapshot.get('guard_failure') is None and snapshot.get('first_cancel_at') is None and snapshot.get('first_alarm_at') is None, 'fixture_precondition_failed: earlier local failure'
    return True


def validate_injection(options, events, receipt):
    phase=options.get('phase')
    if not phase:return True
    assert not any(x.get('kind')=='fixture_precondition_failed' for x in events), 'fixture_precondition_failed: retained event'
    injections=[x for x in events if x.get('kind')=='injection' and x.get('role')+':'+x.get('phase')==phase]
    assert len(injections)==1, 'requested injection missed or duplicated'
    event=injections[0]
    assert event.get('precondition_passed') is True, 'fixture_precondition_failed: no positive precheck'
    check_precondition(options,event)
    # This proves ordering under registered positive entry conditions only.
    # It cannot prove that no concurrent post-injection failure contributed.
    first=receipt.get('first_global_failure')
    assert isinstance(first,dict) and first.get('timestamp') is not None and event.get('monotonic') is not None, 'post-injection failure observation missing'
    assert first['timestamp']>=event['monotonic'], 'fixture_precondition_failed: receipt has earlier global failure'
    return True
