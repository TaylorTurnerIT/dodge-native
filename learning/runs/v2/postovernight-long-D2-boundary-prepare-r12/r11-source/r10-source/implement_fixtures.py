"""Install narrowly scoped positive fixture witnesses; no fixture execution."""
from pathlib import Path
H=Path(__file__).resolve().parent
p=H/'fixture_guards.py';s=p.read_text().replace('import os\n','import os\nfrom fixture_preconditions import validate_injection\n')
s=s.replace("    if options.get('phase'):\n        assert any(x['kind']=='injection' and x['role']+':'+x['phase']==options['phase'] for x in events), 'requested injection missed'","    validate_injection(options,events,receipt)")
p.write_text(s)
p=H/'os_checks.py';s=p.read_text().replace('from fixture_guards import validate_fixture','from fixture_guards import validate_fixture\nfrom fixture_preconditions import preregister')
s=s.replace("options=dict(options,expectation_class=cls,expected_exit=expected)","options=preregister(dict(options,expectation_class=cls,expected_exit=expected))")
# Keep the original 15 cases verbatim, but expose their registration for prechecks.
start=s.index('    cases=[');end=s.index('    for name,options,expected in cases:',start)
cases=s[start:end].replace('    cases=[','CASES=[').replace('\n        (','\n    (').replace('\n    ]','\n]')
s=s[:start]+s[end:];s=s.replace('in cases:','in CASES:')
s=s.replace('\ndef main():','\n'+cases+'\n\ndef main():');p.write_text(s)
p=H/'synthetic.py';s=p.read_text().replace('import processes as owned','import processes as owned\nfrom fixture_preconditions import check_precondition')
s=s.replace('    registered_worker=[None];worker_wait_attempted=[False]',"    registered_worker=[None];worker_wait_attempted=[False]\n    milestones={};execution_seen=[None];guard_seen=[None]")
needle="        fired=True;mutation=options.get('mutation','none')\n        event('injection',phase=phase,mutation=mutation,latch_phase=None if life.ACTIVE is None else life.ACTIVE.phase,live_owned_threads="
replacement="""        # Positive event records from other roles, never missing-file inference.
        observed=dict(milestones)
        for path in root.glob('*-events.jsonl'):
            for line in path.read_text().splitlines():
                try:record=json.loads(line)
                except json.JSONDecodeError:continue  # An in-progress append is not positive evidence.
                if record.get('kind')=='milestone' and record.get('value') is True:
                    observed[record['name']]=True
        pool=life.POOL;active=life.ACTIVE
        guard=guard_seen[0]
        snapshot=dict(latch_phase=None if active is None else active.phase,
            pool_first=None if pool is None else pool.first,pool_until=None if pool is None else pool.until,
            first_global_failure=None if pool is None else pool.first_global,milestones=observed,
            guard_failure=None if guard is None or guard.failure is None else repr(guard.failure),
            first_cancel_at=None if active is None else active.first_cancel_at,
            first_alarm_at=None if active is None else active.first_alarm_at)
        try:check_precondition(options,snapshot)
        except AssertionError as error:
            fired=True
            event('fixture_precondition_failed',phase=phase,error=str(error),**snapshot)
            raise c.Stop(str(error),'publication_failure')
        fired=True;mutation=options.get('mutation','none')
        event('injection',phase=phase,mutation=mutation,precondition_passed=True,**snapshot,live_owned_threads="""
assert needle in s;s=s.replace(needle,replacement)
needle="    real_replace=c.replace_json\n"
replacement="""    def milestone(name):
        milestones[name]=True
        event('milestone',name=name,value=True)
    real_replace=c.replace_json
"""
s=s.replace(needle,replacement)
s=s.replace("        if name:trigger(name+'-before')", "        if name=='receipt' and value.get('accepted') is True:milestone('normal_accepted_publication_prepared')\n        if name:trigger(name+'-before')")
s=s.replace("        real_replace(path,value)\n        if name:trigger(name+'-after')", "        real_replace(path,value)\n        if name=='receipt' and value.get('accepted') is True:milestone('normal_accepted_publication')\n        if name=='terminal' and value.get('internal_decision')=='complete_pending_outer_acceptance':milestone('normal_terminal_publication')\n        if name:trigger(name+'-after')")
s=s.replace("    real_close=c.Guard.close", "    real_start=c.Guard.start\n    def starting(guard):\n        guard_seen[0]=guard\n        return real_start(guard)\n    c.Guard.start=starting\n    real_close=c.Guard.close")
s=s.replace("        if role=='inner' and value.get('kind')=='registered':registered_worker[0]=value['worker_pid']", "        if role=='inner' and value.get('kind')=='registered':\n            registered_worker[0]=value['worker_pid'];milestone('registration_ack_received')")
s=s.replace("        return real_send(channel,value,*a,**kw)\n    life.Channel.send=sending", "        result=real_send(channel,value,*a,**kw)\n        if role=='outer' and value.get('kind')=='start_ack':milestone('outer_gate_ack_sent')\n        if role=='inner' and value.get('kind')=='worker_wait':milestone('worker_wait_sent')\n        if role=='inner' and value.get('kind')=='inner_ready':milestone('inner_ready_sent')\n        return result\n    life.Channel.send=sending")
s=s.replace("            if role=='inner' and owned_role=='worker':trigger('spawn-before-registration')", "            if role=='inner' and owned_role=='worker':\n                milestone('worker_spawned');trigger('spawn-before-registration')")
s=s.replace("                event('registered_worker_live_at_crash',worker_pid=", "                milestone('registered_worker_live_at_crash')\n                event('registered_worker_live_at_crash',worker_pid=")
s=s.replace("        return real_poll(child)\n    owned.Child.poll=polling", "        result=real_poll(child)\n        if result is not None:\n            if role=='inner':milestone('worker_direct_wait_observed')\n            elif role=='outer':milestone('inner_direct_wait_observed')\n        return result\n    owned.Child.poll=polling\n    real_gate=c.worker_gate\n    def gated(args):\n        result=real_gate(args)\n        milestone('worker_handshake_complete')\n        return result\n    c.worker_gate=gated")
p.write_text(s)
# Existing pure controls now register explicit positive normal-entry witnesses.
p=H/'test_r7.py';s=p.read_text().replace('from fixture_guards import validate_fixture','from fixture_guards import validate_fixture\nfrom fixture_preconditions import preregister')
s=s.replace('    return receipt,events,options',"""    if options.get('phase'):
        options=preregister(options)
        injection=next(x for x in events if x['kind']=='injection')
        injection.update(monotonic=100.,precondition_passed=True,latch_phase=options['injection_contract']['expected_latch_phase'],
                         pool_first=None,pool_until=None,first_global_failure=None,guard_failure=None,
                         first_cancel_at=None,first_alarm_at=None,
                         milestones={name:True for name in options['injection_contract']['positive_prerequisites']})
        receipt['first_global_failure']=dict(timestamp=100.1)
    return receipt,events,options""")
needle="        options.update(phase='inner:terminal-after',mutation='crash');events.append(dict(kind='injection',role='inner',phase='terminal-after'))"
replacement="""        options.update(phase='inner:terminal-after',mutation='crash');options=preregister(options)
        events.append(dict(kind='injection',role='inner',phase='terminal-after',monotonic=101.5,
            precondition_passed=True,latch_phase='NORMAL',pool_first=None,pool_until=None,first_global_failure=None,
            guard_failure=None,first_cancel_at=None,first_alarm_at=None,
            milestones={name:True for name in options['injection_contract']['positive_prerequisites']}))
        r['first_global_failure']=dict(timestamp=101.75)"""
assert needle in s;s=s.replace(needle,replacement)
p.write_text(s)
