from pathlib import Path
H=Path(__file__).resolve().parent
p=H/'long_d2.py';s=p.read_text()
s=s.replace("    record_primary_failure(result, primary_error(error, guard))", "    error = primary_error(error, guard)\n    record_primary_failure(result, error)")
s=s.replace("        permission['acknowledged_until'] = deadline\n        return True", "        permission['acknowledged_until'] = deadline\n        result['first_global_failure'] = life.POOL.first_global\n        if life.POOL.first_global is not None:\n            result.update(outcome_fields(life.POOL.first_global['outcome']))\n        return True")
s=s.replace("    except BaseException as error:\n        return dict(status='partial_or_unavailable', path=str(path), error=repr(error))", "    except BaseException as error:\n        if life.POOL is None or life.POOL.until is None:\n            if isinstance(error,Stop) and (guard.failure is not None or time.monotonic()>=deadline or life.ACTIVE is not None and (life.ACTIVE.cancellation_requests or life.ACTIVE.alarm_seen)):\n                raise\n        return dict(status='partial_or_unavailable', path=str(path), error=repr(error))")
s=s.replace("    context=capsule_context(ROOT)\n", "    context=capsule_context(ROOT,verify_inputs=False)\n")
s=s.replace('        p,config,base,identity,pins,lease=context_provider(ROOT)', '        p,config,base,identity,pins,lease=context_provider(ROOT,verify_inputs=False)')
s=s.replace("            at=guard.failure_at if guard is not None else None\n            until=life.notify_failure(error,at)", "            error, descriptor=observed_failure(error,guard,'inner')\n            at=descriptor['timestamp']\n            until=life.notify_failure(error,at)")
s=s.replace("                      cleanup_until_monotonic=until)", "                      cleanup_until_monotonic=until,first_local_failure=life.POOL.first_local,first_global_failure=life.POOL.first_global)")
s=s.replace("                mandatory_failure(args.output/'inner-failure.json',result,until)\n                if guard is not None:\n                    optional_timing(guard,ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl',until)", "                failure_publication(args.output/'inner-failure.json',result,until,guard,\n                    ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl')")
insert='''def failure_publication(path, result, deadline, guard, timing_path):
    """Mandatory receipt attempted first; each optional action has its own catch."""
    try:
        mandatory_failure(path,result,deadline)
    except BaseException as error:
        result['mandatory_failure_publication_error'] = repr(error)
    try:
        if guard is not None:
            optional_timing(guard,timing_path,deadline)
    except BaseException:
        pass


'''
s=s.replace('def worker_failure(error, args, guard, learner, result, permission):',insert+'def worker_failure(error, args, guard, learner, result, permission):')
p.write_text(s)
p=H/'long_d2_executor.py';s=p.read_text()
s=s.replace("                c.mandatory_failure(receipt_path,result,self.pool.until)\n                if self.guard is not None:\n                    c.optional_timing(self.guard,receipt_path.parent/'outer-verification.jsonl',self.pool.until)", "                c.failure_publication(receipt_path,result,self.pool.until,self.guard,receipt_path.parent/'outer-verification.jsonl')")
p.write_text(s)
