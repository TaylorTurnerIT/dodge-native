"""Retained exact preparation edit recipe; writes only its own directory."""
from pathlib import Path
import hashlib,json,shutil,time
H=Path(__file__).resolve().parent; R=H.parent/'postovernight-long-D2-prepare-r4'; ROOT=H.parents[3]
def save(name,v):
 with (H/name).open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
save('start-receipt.json',dict(monotonic=time.monotonic(),budget_seconds=1800,scope='stdlib preparation only'))
files=['docs/implementation-plan-v2.md','docs/SPEC_PRIVILEGED_VIT_RL.md','learning/runs/v2-orchestration/state.json','learning/runs/v2-orchestration/postovernight-long-D2-r2-plan.json']
save('governing-read-receipt.json',dict(files={str(ROOT/p):sha(ROOT/p) for p in files},mutable_excluded_from_freeze=[files[2]],full_text_read=True))
for n in ('long_d2.py','long_d2_executor.py','lifecycle.py','processes.py','legacy_controls.py','test_lifecycle.py','test_worker_ack_contract.py','latch_probe.py','run_checks.py','synthetic.py','run_focused_checks.py'):
 shutil.copyfile(R/n,H/n)
s=(H/'long_d2.py').read_text().replace("PREPARE_REL = 'learning/runs/v2/postovernight-long-D2-prepare-r4'","PREPARE_REL = 'learning/runs/v2/postovernight-long-D2-guard-prepare-r1'").replace('postovernight-long-D2-r1-protocol-r4.json','postovernight-long-D2-r2-protocol-r1.json').replace('66cc36ef1db959bfe4188a3e2d201f8911b3ffc64baeb1d8347be6fd376ab501','b5329fdf58d984c9e38d36119973e5852601b204265a2422e6e476b0952052da')
s=s.replace('HASH_OBSERVER = None','HASH_OBSERVER = None\nVERIFY_LOCAL = threading.local()')
s=s.replace('    return digest.hexdigest()','    stats = getattr(VERIFY_LOCAL, "stats", None)\n    if stats is not None:\n        stats["files"] += 1\n        stats["bytes"] += Path(path).stat().st_size\n    return digest.hexdigest()',1)
s=s.replace('        self.failure = None','        self.timings = []\n        self.active_timing = None\n        self.failure = None',1)
a=s.index('    def full_check(self, force=False):'); b=s.index('    def sample(',a)
s=s[:a]+'''    def full_check(self, force=False):
        trigger = self.clock()
        with self.verify_lock:
            self.check()
            at = self.clock()
            if not force and self.last_full is not None and at - self.last_full < 2:
                return
            previous = self.last_full
            due = trigger if previous is None or force else previous + 2
            row = dict(schema='long_d2_verification_timing_v1', sequence=len(self.timings),
                       trigger_monotonic=trigger, start_monotonic=at, end_monotonic=None,
                       forced=bool(force), thread=threading.current_thread().name,
                       background=threading.current_thread() is self.verify_thread,
                       previous_successful_start_monotonic=previous,
                       trigger_delay_seconds=max(0.0, trigger-due),
                       verify_lock_wait_seconds=at-trigger, components={}, files=0, bytes=0,
                       status='interrupted')
            require(len(self.timings) < 50000, 'Verification telemetry capacity exceeded')
            self.timings.append(row)
            self.active_timing = row
            cpu = time.thread_time()
            VERIFY_LOCAL.stats = row
            try:
                gap = 0 if previous is None else at - previous
                require(gap <= 5, 'Full input verification gap exceeded 5s')
                self.verify()
                end = self.clock()
                # Use consecutive verification starts and include this check's IO.
                # This conservatively bounds every pinned byte's revisit interval.
                gap = max(gap, end-at if previous is None else end-previous)
                self.maximum_full_gap = max(self.maximum_full_gap, gap)
                require(gap <= 5, 'Full input verification gap exceeded 5s')
                self.last_full = at
                self.check()
                row['status'] = 'passed'
            except BaseException as error:
                row.update(status='failed', error=repr(error))
                raise
            finally:
                end = self.clock()
                row.update(end_monotonic=end, duration_seconds=end-at,
                           thread_cpu_seconds=time.thread_time()-cpu,
                           full_gap_seconds=end-at if previous is None else end-previous)
                VERIFY_LOCAL.stats = None
                self.active_timing = None

    def persist_timing(self, path, deadline, permission=lambda: None):
        """Main-thread IO only, after owned verifier teardown. No telemetry thread.

        Rows stay in bounded memory during verification; IO never takes either
        resource lock or runs on the independent resource monitor. A killed
        process can lose unflushed rows; partial/failure receipts retain what is
        safely available. The process lifetime deadline still owns every write.
        """
        require(all(t is None or not t.is_alive() for t in (self.thread,self.verify_thread)),
                'Timing persistence requires owned Guard thread absence')
        path = Path(path)
        path.parent.mkdir(parents=False, exist_ok=True)
        with path.open('x') as stream:
            for row in self.timings:
                permission(); life.remaining(deadline)
                emit(stream, row)
                life.remaining(deadline); permission()
        life.remaining(deadline); permission()
        manifest = dict(schema='long_d2_verification_output_v1', path=str(path),
                        sha256=sha(path), rows=len(self.timings), owned_threads_absent=True,
                        complete=all(r.get('end_monotonic') is not None for r in self.timings))
        save(path.with_suffix('.manifest.json'), manifest)
        life.remaining(deadline); permission()
        return manifest

''' + s[b:]
s=s.replace("                    self.failure = error if isinstance(error, Stop) else Stop(repr(error))","                    self.failure = self.failure or (error if isinstance(error, Stop) else Stop(repr(error)))")
s=s.replace("latched_failure=None if self.failure is None else repr(self.failure))","latched_failure=None if self.failure is None else repr(self.failure),\n                    verification_pass_count=len(self.timings),\n                    interrupted_verification=self.active_timing)")
# Exact same verification operations, instrumented with per-thread component contexts.
s=s.replace('''        verify_files(pins)
        assert_readonly_capsule(ROOT,read_json(ROOT/'capsule-manifest.json'))
        if imported:
            imported['identity'].check_frozen(ORIGINAL_ROOT/p['base_identity_path'],
                 p['base_identity_sha256'],base,ORIGINAL_ROOT)
            check_module_origins(identity,ROOT)''','''        with verification_component('full_pins'):
            verify_files(pins)
        with verification_component('capsule_walks'):
            assert_readonly_capsule(ROOT,read_json(ROOT/'capsule-manifest.json'))
        with verification_component('legacy_frozen_rebuild'):
            if imported:
                imported['identity'].check_frozen(ORIGINAL_ROOT/p['base_identity_path'],
                     p['base_identity_sha256'],base,ORIGINAL_ROOT)
        with verification_component('origins'):
            if imported:
                check_module_origins(identity,ROOT)''')
s=s.replace('''            verify_files(pins)
            assert_readonly_capsule(ROOT,read_json(ROOT/'capsule-manifest.json'))
            if 'legacy_module_origins' in identity:
                check_module_origins(identity,ROOT)''','''            with verification_component('full_pins'):
                verify_files(pins)
            with verification_component('capsule_walks'):
                assert_readonly_capsule(ROOT,read_json(ROOT/'capsule-manifest.json'))
            with verification_component('origins'):
                if 'legacy_module_origins' in identity:
                    check_module_origins(identity,ROOT)''')
# Record outcome once in worker_failure, before ACK or cleanup TERM can arrive.
s=s.replace("    permission['failed'] = True", "    record_primary_failure(result, error)\n    permission['failed'] = True",1)
s=s.replace("            result.update(outcome_fields(failure_outcome(error)),error=repr(error),traceback=traceback.format_exc())","            result['traceback'] = traceback.format_exc()")
s=s.replace("                result.update(outcome_fields(failure_outcome(error)),final_verification_error=repr(error))","                result['final_verification_error'] = repr(error)")
s=s.replace("                result.update(outcome_fields('publication_failure'),stream_close_error=repr(error))","                result['stream_close_error'] = repr(error)")
s=s.replace("        result.update(outcome_fields('cancelled'),cancellation_requests=cancel.cancellation_requests,\n                      cancellation_signal=signal.Signals(cancel.requested_signal).name)","        result.update(cancellation_requests=cancel.cancellation_requests,\n                      cancellation_signal=signal.Signals(cancel.requested_signal).name,\n                      cancellation_secondary=result['outcome'] != 'cancelled')")
s=s.replace("        result.update(outcome_fields('wall_guard'),deadline_expired=True)","        record_primary_failure(result, Stop('Worker deadline expired','wall_guard'))\n        result['deadline_expired'] = True")
s=s.replace("        if learner is not None:\n            worker_write_permission(args,result,permission,learner)\n            save(args.output/'checkpoint-index.json',learner.checkpoints)","        if guard is not None:\n            guard.persist_timing(args.output/'worker-verification.jsonl',\n                life.POOL.deadline(args.started+WORKER_SECONDS),\n                lambda: worker_write_permission(args,result,permission,learner))\n        if learner is not None:\n            worker_write_permission(args,result,permission,learner)\n            save(args.output/'checkpoint-index.json',learner.checkpoints)")
s=s.replace("        authority(True)\n        return code,guard", "        authority(True)\n        guard.persist_timing(ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl',\n                             deadline,lambda: authority(False))\n        return code,guard")
s=s.replace("            if args.output.is_dir():\n                replace_json(args.output/'inner-failure.json',result)","            if args.output.is_dir():\n                guard.persist_timing(ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl',until)\n                replace_json(args.output/'inner-failure.json',result)")
insert='''\n@contextmanager
def verification_component(name):
    row = getattr(VERIFY_LOCAL, 'stats', None)
    start, cpu = time.monotonic(), time.thread_time()
    try:
        yield
    finally:
        if row is not None:
            row['components'][name] = dict(duration_seconds=time.monotonic()-start,
                                          thread_cpu_seconds=time.thread_time()-cpu)


def record_primary_failure(result, error):
    """First failure owns outcome/error. Later cleanup signals are evidence only."""
    if 'primary_failure' not in result:
        primary = dict(outcome=failure_outcome(error), error=repr(error))
        result.update(outcome_fields(primary['outcome']), error=primary['error'], primary_failure=primary)
    else:
        result.setdefault('secondary_failures', []).append(
            dict(outcome=failure_outcome(error), error=repr(error)))

'''
s=s.replace('\ndef worker_failure(',insert+'\ndef worker_failure(')
(H/'long_d2.py').write_text(s)
s=(H/'long_d2_executor.py').read_text()
s=s.replace("'entry-restoration.json','entry-control.json'","'worker-verification.jsonl','worker-verification.manifest.json',\n           'entry-restoration.json','entry-control.json'")
s=s.replace('''                c.verify_files(pins)
                c.verify_files(self.registration['pins'])
                c.assert_readonly_capsule(c.ROOT,c.read_json(c.ROOT/'capsule-manifest.json'))''','''                with c.verification_component('full_pins'):
                    c.verify_files(pins)
                    c.verify_files(self.registration['pins'])
                with c.verification_component('capsule_walks'):
                    c.assert_readonly_capsule(c.ROOT,c.read_json(c.ROOT/'capsule-manifest.json'))''')
s=s.replace("            self.closed=True", "            self.guard.persist_timing(receipt_path.parent/'outer-verification.jsonl',\n                                      self.t0+NORMAL_SECONDS,lambda: self.authority(False))\n            self.closed=True")
s=s.replace("                c.replace_json(receipt_path,result)\n                life.remaining(self.pool.until)", "                if self.guard is not None:\n                    self.guard.persist_timing(receipt_path.parent/'outer-verification.jsonl',self.pool.until)\n                c.replace_json(receipt_path,result)\n                life.remaining(self.pool.until)")
(H/'long_d2_executor.py').write_text(s)
# Adjust fixture evidence for new supervision-only timing writes; no ML body change.
s=(H/'test_lifecycle.py').read_text().replace('66cc36ef1db959bfe4188a3e2d201f8911b3ffc64baeb1d8347be6fd376ab501','b5329fdf58d984c9e38d36119973e5852601b204265a2422e6e476b0952052da')
(H/'test_lifecycle.py').write_text(s)
s=(H/'test_worker_ack_contract.py').read_text().replace('receipt=lambda:{})','receipt=lambda:{},persist_timing=lambda *a: None)')
(H/'test_worker_ack_contract.py').write_text(s)
save('initial-source-manifest.json',{p.name:sha(p) for p in H.glob('*.py')})
