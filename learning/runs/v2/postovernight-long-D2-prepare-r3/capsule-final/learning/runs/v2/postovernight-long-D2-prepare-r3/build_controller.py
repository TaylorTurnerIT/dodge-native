"""Reconstruct the focused r3 copy from frozen r2; preparation helper only."""
from pathlib import Path
import ast
HERE=Path(__file__).resolve().parent
old=(HERE.parent/'postovernight-long-D2-prepare-r2/long_d2.py').read_text()
s=old.replace('postovernight-long-D2-prepare-r2','postovernight-long-D2-prepare-r3').replace('postovernight-long-D2-r1-protocol-r2.json','postovernight-long-D2-r1-protocol-r3.json').replace('f662a4aba18e144098faeb01d398b67f489aea7549a9ebe4a5959f993e1cff09','6a7ffe59551fd12f4a6fd316c6ab626d03e92a7ec25f77dc34fce30837fa592d')
s=s.replace('import traceback\n','import traceback\nimport socket\nimport lifecycle as life\nimport processes as owned\n')
a=s.index('class Stop(RuntimeError):');b=s.index('\n\ndef require',a)
s=s[:a]+'Stop = life.Stop\nINNER_SECONDS = 7170\n'+s[b:]
a=s.index('_ACTIVE_CANCELLATION = None');b=s.index('\n\nclass Guard:',a)
s=s[:a]+'''@contextmanager
def cancellation_signals():
    require(life.ACTIVE is not None, 'Subprocess lifetime latch required')
    yield life.ACTIVE  # Borrow only. Never restore handlers, masks or timer.


@contextmanager
def absolute_alarm(deadline):
    require(life.ACTIVE is not None and deadline <= life.ACTIVE.deadline,
            'Nested/new timer ownership forbidden')
    life.ACTIVE.check()
    yield
    life.ACTIVE.check()
'''+s[b:]
a=s.index('@contextmanager\ndef absolute_alarm',s.index('class Guard:'));b=s.index('\n\ndef counter_report',a)
s=s[:a]+s[b:]
s=s.replace('self.thread.start()','life.start_thread(self.thread)').replace('self.verify_thread.start()','life.start_thread(self.verify_thread)')
s=s.replace('self.failure = None\n        self.maximum','self.failure = None\n        self.failure_at = None\n        self.maximum')
s=s.replace('self.failure = error if isinstance(error, Stop) else Stop(repr(error))','self.failure_at = self.failure_at or self.clock()\n                    self.failure = error if isinstance(error, Stop) else Stop(repr(error))')
s=s.replace('thread.join(timeout=0.5)','thread.join(timeout=life.remaining(life.POOL.deadline(self.deadline) if life.POOL else self.deadline, 0.5))')
# The worker exception/finalization exception are the sole permitted ML-body exception.
a=s.index('def worker(args, context):');b=s.index('\n\ndef revoke_terminal',a)
w=s[a:b]
w=w.replace("result.update(outcome_fields(failure_outcome(error)),error=repr(error),traceback=traceback.format_exc())","worker_failure(error, args, guard, learner)\n            result.update(outcome_fields(failure_outcome(error)),error=repr(error),traceback=traceback.format_exc())")
w=w.replace('api.absolute_deadline','api.absolute_deadline')
w=w.replace('absolute_deadline=args.started+BUDGET','absolute_deadline=args.started+WORKER_SECONDS')
w=w.replace('                verify()\n                require(time.monotonic()<args.started+BUDGET',"                if result_code(result) != 1:\n                    verify()\n                require(time.monotonic()<life.POOL.deadline(args.started+WORKER_SECONDS)")
w=w.replace("result.update(outcome_fields(failure_outcome(error)),final_verification_error=repr(error))","worker_failure(error, args, guard, learner)\n                result.update(outcome_fields(failure_outcome(error)),final_verification_error=repr(error))")
w=w.replace("result.update(outcome_fields('publication_failure'),stream_close_error=repr(error))","worker_failure(error, args, guard, learner)\n                result.update(outcome_fields('publication_failure'),stream_close_error=repr(error))")
w=w.replace('actual_import_origins=check_module_origins(identity,ROOT)','actual_import_origins=(check_module_origins(identity,ROOT) if result_code(result)!=1 else {})')
w=w.replace('args.started+BUDGET','life.POOL.deadline(args.started+WORKER_SECONDS)')
w=w.replace("    save(args.output/'long-worker-result.json',result)","    if result_code(result)==1 and life.POOL.until is None:\n        worker_failure(Stop(result['outcome']),args,guard,learner)\n    life.remaining(life.POOL.deadline(args.started+WORKER_SECONDS))\n    save(args.output/'long-worker-result.json',result)\n    life.remaining(life.POOL.deadline(args.started+WORKER_SECONDS))")
s=s[:a]+'''def worker_failure(error, args, guard, learner):
    at = guard.failure_at if guard is not None and guard.failure_at is not None else None
    deadline = life.notify_failure(error, at)
    if learner is not None:
        learner.api.absolute_deadline = deadline
    return deadline


'''+w+s[b:]
a=s.index('def revoke_terminal');s=s[:a]+(HERE/'supervisor_fragment.txt').read_text()
(HERE/'long_d2.py').write_text(s)
