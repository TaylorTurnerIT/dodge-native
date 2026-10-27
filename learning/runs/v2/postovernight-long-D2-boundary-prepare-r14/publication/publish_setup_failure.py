"""Failure-specific publication after a wrapper setup error. Publication only: no source edit, no test run, no retry."""
from pathlib import Path
import datetime, difflib, hashlib, json, subprocess, sys, time

H = Path(__file__).resolve().parents[1]
ROOT = H.parents[3]
sys.path.insert(0, str(H))
import current_delta as delta  # stdlib only

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(name, value):
    with (H / name).open('x') as s:
        json.dump(value, s, indent=2, sort_keys=True, allow_nan=False)
        s.write('\n')

def udiff(old, new, a, b):
    return ''.join(difflib.unified_diff(old.read_text().splitlines(True) if old.exists() else [], new.read_text().splitlines(True), fromfile=a, tofile=b))

started = json.loads((H / 'start.json').read_text())
frozen = json.loads((H / 'source-manifest.json').read_text())['files']
now_inv = {n: dict(sha256=sha(H / n), bytes=(H / n).stat().st_size) for n in frozen}
unchanged = now_inv == frozen
(H / 'diffs').mkdir()
changed, combined = [], []
for p in sorted(x for x in H.iterdir() if x.is_file() and x.suffix in ('.py', '.json') and x.name != 'start.json'):
    old = H / 'r12-source' / p.name
    if p.name in ('input-manifest.json', 'base-source-manifest.json', 'source-manifest.json', 'state.context.snapshot.json'):
        continue
    text = udiff(old, p, 'r12-source/' + p.name, 'r14/' + p.name)
    if text:
        (H / 'diffs' / (p.name + '.diff')).write_text(text)
        combined.append(text)
        changed.append(p.name)
(H / 'candidate.diff').write_text(''.join(combined))
(H / 'diffs' / 'long_d2.py.vs-r11.diff').write_text(udiff(H / 'r11-source/long_d2.py', H / 'long_d2.py', 'r11-source/long_d2.py', 'r14/long_d2.py'))
(H / 'diffs' / 'protocol-r10-vs-r9.diff').write_text(udiff(H / 'r12-source/protocol-r9-proposal.json', H / 'protocol-r10-proposal.json', 'protocol-r9', 'protocol-r10'))
projection = dict(schema='r14_static_projection_not_test_evidence_v1',
    projected_r14_to_r11_equals_exact_r11=delta.project_to_r11_with_sha((H / 'long_d2.py').read_text(), sha(H / 'protocol-r10-proposal.json')) == (H / 'r11-source/long_d2.py').read_text(),
    projected_r14_to_r12_equals_exact_r12=delta.project_to_r12((H / 'long_d2.py').read_text()).replace(sha(H / 'protocol-r10-proposal.json'), delta.R12_SHA) == (H / 'r12-source/long_d2.py').read_text(),
    other_controller_files_byte_equal_r11={n: (H / n).read_bytes() == (H / 'r11-source' / n).read_bytes() for n in
        ('long_d2_executor.py', 'lifecycle.py', 'processes.py', 'boundary_integrity.py', 'freeze.py', 'source_equality.py', 'fixture_guards.py', 'fixture_preconditions.py', 'os_checks.py', 'synthetic.py', 'stress.py', 'rehearsal.py', 'parent_command.py', 'model_r11.py')},
    note='Static string/byte analysis only. This is NOT a registered test result; no candidate import or test execution occurred.')
save('byte-projection-report.json', projection)
precheck = json.loads((H / 'unit-stage/setup-precheck.json').read_text())
save('setup-failure.json', dict(schema='r14_setup_failure_v1', stage='unit_stage.py wrapper before test child launch',
    exception_text="TypeError: 'dict' object is not callable at unit_stage.py line 122 (now() in command.json registration); the except handler then failed again at line 143 (now()).",
    cause="My new precheck code assigned a local dict named `now` inside main(), shadowing the module-level now() timestamp function. Defect in the wrapper only; candidate source and tests are not implicated.",
    test_child_launched=False, validation_attempts=0, test_invocations=0, command_json_written=False,
    raw_result=json.loads((H / 'unit-stage/raw-result.json').read_text()),
    setup_precheck_passed=dict(existing_methods_exact=precheck['existing_methods_exact'], existing_test_sources_exact=precheck['existing_test_sources_exact'],
        new_methods=precheck['new_methods'], unchanged_inherited_methods=precheck['unchanged_inherited_methods'], changed_inherited_methods=precheck['changed_inherited_methods'],
        input_bindings_all_match=precheck['input_bindings_all_match'], original_fixture_exact=precheck['original_fixture_exact'], unique_names=precheck['unique_names']),
    rule_applied='Parent rule: unexpected mutating setup failure stops without patch or retry. Wrapper not patched; stage not rerun.',
    suggested_parent_fix_not_applied="Rename the local `now` dict/lists in unit_stage.py::main (the `now_text, now_lines, now = method_texts(...)` line and its uses) so module-level now() stays callable.",
    source_inventory_unchanged=unchanged))
elapsed = time.time() - started['start_epoch']
result = dict(schema='r14_implementation_result_v1', status='setup_failure_no_test_run', candidate=str(H), base='frozen r12',
    source_manifest_sha256=sha(H / 'source-manifest.json'), source_members=len(frozen), source_frozen_unchanged=unchanged,
    candidate_diff=dict(path='candidate.diff', sha256=sha(H / 'candidate.diff')), changed_files=changed,
    protocol_r10_proposal=dict(path='protocol-r10-proposal.json', sha256=sha(H / 'protocol-r10-proposal.json'), external_publication=False),
    tests=dict(registered=143, planned_inherited=112, planned_new=31, executed=0, passed=0, unrun=143, test_invocations=0),
    production_semantic_change='Guard.full_check early callback catch before interval cleanup; masked cleanup re-raises original callback with cleanup as __cause__',
    no_test_evidence=True, routine_read_only_discovery_errors=[], campaign_retries=0, scope_deviations=[],
    actual_elapsed_seconds_through_result=elapsed, budget_seconds=1800, training_authorization_7200s_unused_parent_held=True)
save('implementation-result.json', result)
(H / 'PARENT-NEXT.md').write_text("""# r14 source prepared; stage stopped at wrapper setup error (no tests ran)

Result: `setup_failure_no_test_run`. The single registered stage never launched its child: `unit_stage.py` crashed before `command.json` (`TypeError: 'dict' object is not callable`), because my new precheck code named a local dict `now`, shadowing the `now()` timestamp function. Per the parent rule (unexpected mutating setup failure), I stopped: no wrapper patch, no retry, no test invocation. Zero of 143 registered methods ran (112 inherited + 31 new). There is no test evidence, so do not treat r14 as validated.

What exists, frozen and unmodified after the failure: candidate source (see `source-manifest.json`, `candidate.diff`, `diffs/`), `protocol-r10-proposal.json` (derived from exact r12 protocol-r9 bytes, pinned in controller), the migrated four static test expectations, `test_r14.py` (31 methods: adapted scheduling, chronology, scanner, r12 negative control), `current_delta.py` and the unrun runner. `setup-precheck.json` passed: 112 inherited names exact, 108 bodies byte-identical to r12, exactly 4 migrated, all 215 r12 + 20 additional input bindings matched.

Production change: `Guard.full_check` latches the callback exception and its actual catch timestamp inside the interval context before cleanup can raise. If cleanup masks it, the original callback exception is re-raised with the cleanup error as `__cause__`, the cleanup error is stored as `cleanup_error`, and the process latch still records the later cancellation. `observed_failure`, `FailurePool`, executor, lifecycle, processes, boundary_integrity, fixtures and consumers are unchanged.

`byte-projection-report.json` is static string analysis, not a registered test. See `setup-failure.json` for the one-line wrapper fix I did not apply. A new authorized owned stage (r15 or a parent-approved rerun of the stage with that fix) is needed before any review. Training authorization (7200 s) remains unused and parent-held.
""")
cache = H / 'json-validation-pycache'
cache.mkdir()
val = []
for p in sorted(H.rglob('*.json')):
    if cache in p.parents or any(x in p.parts for x in ('original-source', 'r6-source', 'r9-source', 'r10-source', 'r11-source', 'r12-source', 'sources')):
        continue
    r = subprocess.run(['learning/.venv/bin/python', '-B', '-m', 'json.tool', str(p)], cwd=ROOT, capture_output=True,
        env=dict(PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=str(cache), PATH='/usr/bin:/bin'))
    val.append(dict(path=str(p.relative_to(H)), returncode=r.returncode))
save('json-validation.json', dict(validated=len(val), all_ok=all(v['returncode'] == 0 for v in val), files=val))
excl = ('evidence-manifest.json', 'completion-receipt.json')
files = {str(p.relative_to(H)): dict(sha256=sha(p), bytes=p.stat().st_size) for p in sorted(H.rglob('*')) if p.is_file() and p.name not in excl and cache not in p.parents}
save('evidence-manifest.json', dict(schema='r14_evidence_manifest_v1', acyclic=True, excludes=list(excl), files=files))
done = time.time() - started['start_epoch']
save('completion-receipt.json', dict(schema='r14_completion_v1', completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    actual_elapsed_seconds=done, budget_seconds=1800, in_budget=done <= 1800, status=result['status'], test_invocations=0,
    evidence_manifest_sha256=sha(H / 'evidence-manifest.json'), implementation_result_sha256=sha(H / 'implementation-result.json'),
    no_patch_or_retry=True, source_frozen=unchanged))
print(json.dumps(dict(status=result['status'], elapsed=done, evidence_files=len(files), source_unchanged=unchanged, projection=projection['projected_r14_to_r11_equals_exact_r11'])))
