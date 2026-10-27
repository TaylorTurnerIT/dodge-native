"""One-time transformation of retained rejected orchestration, never learner sources."""
from pathlib import Path
H=Path(__file__).resolve().parent
p=H/'long_d2.py';s=p.read_text()
s=s.replace('import processes as owned','import processes as owned\nimport boundary_integrity as integrity')
s=s.replace('postovernight-long-D2-guard-prepare-r1','postovernight-long-D2-boundary-prepare-r2').replace('postovernight-long-D2-r2-protocol-r1.json','postovernight-long-D2-r2-protocol-r3.json').replace('b5329fdf58d984c9e38d36119973e5852601b204265a2422e6e476b0952052da','6dc974873745c9eb8adeed178dd65c0c10907b6ca6195fc9a1b26a20ccbed054')
a=s.index('    pins = {str(root / k):v for k,v in manifest[\'files\'].items()}');b=s.index('    require(sha(ORIGINAL_ROOT / p[\'base_identity_path\'])',a)
s=s[:a]+'''    classification_path = root / PREPARE_REL / 'classification.json'
    require(sha(classification_path) == identity['classification_sha256'], 'Classification digest differs')
    classification = read_json(classification_path)
    pins = dict(classification['B'])
    # Root envelopes form a DAG and are excluded from leaf classification.
    # External registration is anchored by parent-held invocation SHA, not itself.
    roots = {str(root/k):v for k,v in manifest['files'].items()}
    roots[str(manifest_path)] = sha(manifest_path)
    roots[str(ORIGINAL_ROOT/PREPARE_REL/'long-identity.json')] = sha(identity_path)
    roots[str(ORIGINAL_ROOT/PREPARE_REL/'classification.json')] = identity['classification_sha256']
    pins = integrity.merge_bindings(pins, roots)
    if verify_inputs:
        verify_files(pins)
''' +s[b:]
s=s.replace("identity['version'] == 'teacher_long_D2_identity_v1'", "identity['version'] == 'teacher_long_D2_boundary_identity_v1'")
# Pure endpoint only, child context never expands archive union.
s=s.replace('    context = capsule_context(root)\n    p, config, base, identity, pins, lease = context','    context = capsule_context(root)\n    provenance = integrity.verify(context, root, endpoint=\'preflight\')\n    p, config, base, identity, pins, lease = context').replace("project_torch_native_imported=False, campaign_output_created=False)","project_torch_native_imported=False, campaign_output_created=False, provenance=provenance)")
a=s.index('    """Independent resource/lease and full-byte monitors');b=s.index('    def __init__',a)
s=s[:a]+'''    """Independent safety observer and synchronous declared byte boundaries.

    No periodic integrity thread, interval, revisit-age gate or content cache.
    Resource/lease observation remains independent during boundary file IO.
    """
'''+s[b:]
s=s.replace('        self.timings = []','        self.timings = []\n        self.boundaries = []')
a=s.index('    def full_check(self, force=False):');b=s.index('    def persist_timing',a)
s=s[:a]+'''    def full_check(self, force=False):
        if not force:
            self.check()
            return
        with self.verify_lock:
            self.check()
            at = self.clock()
            row = dict(sequence=len(self.boundaries), start_monotonic=at, verdict='incomplete')
            require(len(self.boundaries) < 50000, 'Boundary evidence capacity exceeded')
            self.boundaries.append(row)
            cpu = time.thread_time()
            stats = dict(files=0, bytes=0, components={})
            VERIFY_LOCAL.stats = stats
            try:
                observation = self.verify()
                self.last_full = at
                self.check()
                row.update(verdict='passed', observation=observation)
            except BaseException as error:
                row.update(verdict='failed', error=repr(error))
                self.failure_at = self.failure_at or self.clock()
                self.failure = self.failure or (error if isinstance(error, Stop) else Stop(repr(error)))
                raise
            finally:
                row.update(end_monotonic=self.clock(), duration_seconds=self.clock()-at,
                           thread_cpu_seconds=time.thread_time()-cpu, **stats)
                VERIFY_LOCAL.stats = None
                self.timings.append(dict(row))

'''+s[b:]
s=s.replace('        if full:\n            self.full_check(force)','        if full and force:\n            self.full_check(True)')
s=s.replace("                    if self.last_full is not None:\n                        require(self.clock()-self.last_full <= 5, 'Full input verification gap exceeded 5s')\n",'')
a=s.index('        def verify_monitor():');b=s.index('    def close(self):',a);s=s[:a]+s[b:]
s=s.replace('                    maximum_full_input_gap_seconds=self.maximum_full_gap,','                    integrity_policy=\'declared_boundaries_no_fixed_revisit\',')
s=s.replace("                    interrupted_verification=self.active_timing)","                    interrupted_verification=self.active_timing, boundary_count=len(self.boundaries),\n                    boundary_verdicts=[r['verdict'] for r in self.boundaries])")
a=s.index('def primary_error(error, guard):');b=s.index('\ndef worker_failure',a)
s=s[:a]+'''def observed_failure(error, guard=None, role='unknown'):
    candidates = []
    now = time.monotonic()
    if guard is not None and guard.failure is not None and guard.failure_at is not None:
        candidates.append((guard.failure_at, guard.failure, 'safety_monitor', 'actual_guard_observation', None))
    latch = life.ACTIVE
    if latch is not None:
        if latch.first_cancel_at is not None:
            candidates.append((latch.first_cancel_at, Stop('Cancellation latched','cancelled'), 'cancel', 'signal_observed_sender_unknown', latch.requested_signal))
        if latch.first_alarm_at is not None:
            candidates.append((latch.first_alarm_at, Stop('Lifetime wall alarm','wall_guard'), 'alarm', 'signal_observed', int(signal.SIGALRM)))
        if latch.deadline is not None and now >= latch.deadline:
            candidates.append((latch.deadline, Stop('Absolute wall deadline','wall_guard'), 'deadline', 'absolute_registered_deadline', None))
    candidates.append((now, error, 'exception_observed', 'catch_observation_not_construction', None))
    at, primary, kind, basis, number = min(candidates, key=lambda item:item[0])
    descriptor = dict(timestamp=at, kind=kind, outcome=failure_outcome(primary), role=role, timing_basis=basis, signal=number)
    primary.first_failure_descriptor = descriptor
    return primary, descriptor


def primary_error(error, guard):
    return observed_failure(error, guard, 'worker')[0]


def record_primary_failure(result, error):
    descriptor = getattr(error, 'first_failure_descriptor', None)
    if descriptor is None:
        error, descriptor = observed_failure(error)
    if 'first_local_failure' not in result:
        result['first_local_failure'] = descriptor
    current = result.get('first_global_failure')
    if current is None or descriptor['timestamp'] < current['timestamp']:
        result['first_global_failure'] = descriptor
        primary = dict(outcome=failure_outcome(error), error=repr(error), descriptor=descriptor)
        result.update(outcome_fields(primary['outcome']), error=primary['error'], primary_failure=primary)
    else:
        result.setdefault('secondary_failures', []).append(descriptor)


def optional_timing(guard, path, deadline, permission=lambda: None):
    """Best effort once; retained partial bytes are evidence, never authority."""
    global HASH_OBSERVER
    previous = HASH_OBSERVER
    try:
        if life.POOL is not None and life.POOL.until is not None:
            HASH_OBSERVER = lambda: life.remaining(life.POOL.until)
        if Path(path).exists():
            return dict(status='existing_partial_or_complete', path=str(path))
        value = guard.persist_timing(path, deadline, permission)
        return dict(status='complete', manifest=value)
    except BaseException as error:
        return dict(status='partial_or_unavailable', path=str(path), error=repr(error))
    finally:
        HASH_OBSERVER = previous


def mandatory_failure(path, result, deadline):
    global HASH_OBSERVER
    previous = HASH_OBSERVER
    HASH_OBSERVER = lambda: life.remaining(deadline)
    try:
        life.remaining(deadline)
        replace_json(path, result)
        life.remaining(deadline)
        return True
    finally:
        HASH_OBSERVER = previous

'''+s[b:]
# Verification callback lives outside protected ML try.
s=s.replace('    imported={}\n', '    imported={}\n    final_runtime = {}\n')
a=s.index('    def verify():',s.index('def worker(args'));b=s.index('    with cancellation_signals()',a)
s=s[:a]+'''    def verify():
        observation = integrity.verify(context, ROOT)
        if imported:
            imported['identity'].check_frozen(ORIGINAL_ROOT/p['base_identity_path'],
                 p['base_identity_sha256'],base,ORIGINAL_ROOT)
            origins = check_module_origins(identity,ROOT)
            runtime = integrity.runtime_check(identity,ORIGINAL_ROOT)
            runtime['project_origins'] = origins
            final_runtime.clear(); final_runtime.update(runtime)
            observation.update(legacy='genuine_unchanged_check_frozen', runtime=runtime)
        else:
            integrity.runtime_check(identity,ORIGINAL_ROOT)
            observation['legacy'] = 'preimport_byte_subset_only'
        return observation
'''+s[b:]
s=s.replace("    result.update(run_id=p['run_id'],protocol_sha256=PROTOCOL_SHA256,", "    if result_code(result) != 1:\n        result['integrity_summary'] = integrity.worker_summary(identity,guard,final_runtime,lease)\n    result.update(run_id=p['run_id'],protocol_sha256=PROTOCOL_SHA256,",1)
# Telemetry cannot stop mandatory worker evidence. ACK permissions still surround IO.
s=s.replace("            guard.persist_timing(args.output/'worker-verification.jsonl',", "            result['optional_timing'] = optional_timing(guard,args.output/'worker-verification.jsonl',")
# Inner B callback replaces historical hotpath and returns observation.
a=s.index('        def verify():',s.index('def supervise_owned'));b=s.index('        guard=guard_factory',a)
s=s[:a]+'''        def verify():
            return integrity.verify((p,config,base,identity,pins,lease), ROOT)
'''+s[b:]
s=s.replace("            require(time.monotonic()-guard.last_full<=5, 'Final full-pin observation age exceeded')\n",'')
s=s.replace("        guard.persist_timing(ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl',", "        optional_timing(guard,ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl',")
s=s.replace("                guard.persist_timing(ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl',until)\n                replace_json(args.output/'inner-failure.json',result)", "                mandatory_failure(args.output/'inner-failure.json',result,until)\n                if guard is not None:\n                    optional_timing(guard,ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl',until)")
p.write_text(s)
