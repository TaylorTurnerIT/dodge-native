"""Owned source preparation/finalization only; never dispatches a campaign."""
import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path

OWN = Path(__file__).resolve().parent
ROOT = OWN.parents[3]
BASE = OWN.parent/'progressive1000-supervisor-nonreaping-parent-completion-20261026-r5'
ACCEPTED = OWN.parent/'progressive1000-shared-runtime-staticmethod-repair-sol-20261026-r2'
ASSEMBLY = OWN.parent/'progressive1000-matched-run-parent-assembly-20261026-r1'
SPENT = 'progressive1000-confirmed324-20261026-r1-replica-1-control_constant_3e-5'
BASE_SHA = 'fd54444b88e80175e7acbef2d37f0d8b613c0018cb6110e85a1ded0e88cfe579'
INDEX_SHA = '7144e7ab3852eac4307e64fecf884d1dc8b21a769f48267d065cf679b3bedaef'


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(name, value):
    path = OWN/name
    assert path.resolve().is_relative_to(OWN)
    with path.open('x') as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2)+'\n')


def metadata(paths):
    """Stat only: never open checkpoint, metric, table, lease or marker payloads."""
    result = {}
    for root in paths:
        for directory, dirs, files in os.walk(root, followlinks=False):
            for path in [Path(directory), *(Path(directory)/n for n in dirs+files)]:
                s = path.lstat()
                result[str(path)] = dict(mode=s.st_mode, size=s.st_size,
                    mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns, inode=s.st_ino)
    return result


def controls(path):
    text = path.read_text()
    return {node.name: ast.get_source_segment(text, node) for node in ast.walk(ast.parse(text))
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')}


def prepare():
    assert sha(BASE/'source-manifest.json') == BASE_SHA
    assert sha(ASSEMBLY/'final-registration-index.json') == INDEX_SHA
    baseline = read(BASE/'source-manifest.json')
    index = read(ASSEMBLY/'final-registration-index.json')
    assert len(index['registrations']) == 6
    immutable = {str(BASE/'source-manifest.json'): BASE_SHA,
                 str(ASSEMBLY/'final-registration-index.json'): INDEX_SHA}
    for name, digest in baseline['files'].items():
        assert sha(BASE/name) == digest
        immutable[str(BASE/name)] = digest
    accepted = {}
    for name in ('source-manifest.json', 'runtime-manifest.json'):
        path = ACCEPTED/name
        accepted[name] = dict(path=str(path), sha256=sha(path))
        immutable[str(path)] = sha(path)
    assert accepted['source-manifest.json']['sha256'] == 'be7b8b3c9ef90d1e820df417f54863b6943fb746c451105078923916f19a04a2'
    roots = [BASE, ACCEPTED]
    for item in index['registrations']:
        path = Path(item['registration'])
        assert sha(path) == item['sha256']
        immutable[str(path)] = item['sha256']
        roots.append(path.parent)
    failure_paths = [ASSEMBLY/SPENT/'execution-exit.json',
                     ASSEMBLY/SPENT/'parent-terminal-audit.json',
                     BASE/'dispatch'/SPENT/'observation.json']
    for path in failure_paths:
        immutable[str(path)] = sha(path)
    audit = read(failure_paths[1])
    observation = read(failure_paths[2])
    execution = read(failure_paths[0])
    # Explicit field allowlists: no performance tables or checkpoint payloads.
    identity = {key: audit[key] for key in ('schema', 'status', 'run_id', 'completed_updates',
        'first_failure', 'raw_observer_exit_code', 'raw_worker_exit_code', 'directly_reaped',
        'independent_process_groups', 'immutable_inputs_dependencies_and_cache_postflight_pass',
        'partial_checkpoints', 'resource_samples', 'remaining_five_runs', 'evidence_limits',
        'comparison_endpoint_complete', 'checkpoint_acceptance', 'marker_and_transition_claim_preserved')}
    assert identity['completed_updates'] == 41 and identity['raw_worker_exit_code'] == -15
    assert identity['immutable_inputs_dependencies_and_cache_postflight_pass'] is True
    assert [x['global_update'] for x in identity['partial_checkpoints']] == [12, 24, 36]
    save('actual-failure-metadata.json', dict(parent_audit=identity, execution=execution,
        observer={key: observation[key] for key in ('status', 'first_event', 'error',
            'traceback', 'actual_worker_launch_count', 'observed_worker_raw_exit',
            'directly_reaped', 'owned_group_absent', 'worker_group_absent',
            'cleanup', 'cleanup_signals', 'deadline_consumed', 'elapsed_seconds')},
        evidence_paths=[str(p) for p in failure_paths], checkpoint_payloads_read=False,
        checkpoint_hashes='Inherited parent-audit metadata only; payloads not rehashed or restored.',
        authority='Spent registration remains closed. No retry, replacement or terminal60 endpoint.'))
    files = sorted([*baseline['files'], 'tests/delayed_ps.py', 'tests/test_ps_deadlines.py',
                    'tests/run_ps_controls.py', 'prepare_artifacts.py'])
    for name in files:
        if name.endswith('.py'):
            ast.parse((OWN/name).read_text(), filename=name)
    save('reviewed-source-manifest.json', baseline)
    save('source-manifest.json', dict(schema='progressive1000_ps_timeout_repair_source_manifest_v6',
        files={name: sha(OWN/name) for name in files}))
    patch = []
    changed = []
    for name in files:
        prior = BASE/name
        after = OWN/name
        before = prior.read_text() if name in baseline['files'] else ''
        if before == after.read_text():
            continue
        patch.extend(difflib.unified_diff(before.splitlines(keepends=True),
            after.read_text().splitlines(keepends=True),
            fromfile='a/'+name if before else '/dev/null', tofile='b/'+name))
        changed.append(dict(path=name, prior_sha256=sha(prior) if before else None,
                            sha256=sha(after)))
    with (OWN/'exact-input-diff.patch').open('x') as stream:
        stream.write(''.join(patch))
    unchanged_runtime = ['binding.py', 'terminal.py', 'execute_once.py', 'dependency-binding.json']
    assert all(sha(BASE/name) == sha(OWN/name) for name in unchanged_runtime)
    old = (BASE/'observe.py').read_text()
    expected = old.replace('def process_rows():\n', 'def process_rows():\n    # The active supervisor SIGALRM enforces the original work/total budget.\n').replace('capture_output=True, text=True, check=True, timeout=1)', 'capture_output=True, text=True, check=True)')
    assert (OWN/'observe.py').read_text() == expected
    reuse = {}
    for name, count in (('test_bindings.py', 11), ('test_real_processes.py', 14)):
        prior, current = controls(BASE/'tests'/name), controls(OWN/'tests'/name)
        assert len(prior) == count and prior == current
        reuse[name] = dict(original_count=count, unchanged=sorted(prior), adapted=[], added=[])
    assert len(controls(OWN/'tests/test_ps_deadlines.py')) == 4
    save('control-reuse.json', dict(original_controls_retained=25, original_test_bodies_byte_identical=True,
        suites=reuse, added_real_boundary_controls=4, total_controls=29,
        support_adaptations={
            'tests/test_bindings.py':'Retain every fake fixture directory; test bodies unchanged.',
            'tests/run_controls.py':'Route retained fake evidence under report directory; stream exclusive log.',
            'tests/run_real_controls.py':'Unchanged: original 14-control runner remains at 15 CPU / 55 wall seconds.',
            'tests/stdlib_child.py':'Unchanged: original 3 CPU / 18 wall seconds.',
            'tests/run_ps_controls.py':'Separate four-method suite, 15 CPU / 30 wall seconds; narrow owned ps-helper SIGKILL audit allowance for real subprocess.run cleanup.',
            'tests/delayed_ps.py':'Owned 1 CPU / 8 wall second helper delays inside real subprocess.run, then execs read-only ps or exits 23.',
            'tests/test_ps_deadlines.py':'Reuse original synthetic gates/direct worker ownership; intercept only ps Popen executable, retain real run/communicate and existing work/total SIGALRM. Shortened synthetic test clocks only.'}))
    save('diff-index.json', dict(base=str(BASE), base_source_manifest_sha256=BASE_SHA,
        source_manifest_sha256=sha(OWN/'source-manifest.json'), changed=changed,
        runtime_byte_identical=unchanged_runtime,
        observer_change='Only remove independent timeout=1; add budget-owner comment. All other bytes unchanged.',
        patch_sha256=sha(OWN/'exact-input-diff.patch')))
    (OWN/'templates').mkdir()
    templates = []
    for item in index['registrations']:
        envelope = read(BASE/'templates'/(item['run_id']+'.envelope.json'))
        assert envelope['registration'] == item['registration']
        assert envelope['registration_sha256'] == item['sha256']
        assert envelope['started'] is None and envelope['launch_approval_sha256'] is None
        spent = item['run_id'] == SPENT
        envelope['status'] = 'SPENT_CLOSED_NO_RETRY_NO_LAUNCH' if spent else 'DRAFT_NO_LAUNCH'
        if not spent:
            envelope['control'] = str(OWN/'dispatch'/item['run_id'])
            envelope['cancel_path'] = str(OWN/'dispatch'/('cancel-'+item['run_id']))
        envelope['pins'] = {str(OWN/Path(p).name) if Path(p).parent == BASE else p:
            sha(OWN/Path(p).name) if Path(p).parent == BASE else digest
            for p, digest in envelope['pins'].items()}
        for path, digest in envelope['pins'].items():
            assert sha(path) == digest
            if not Path(path).is_relative_to(OWN):
                immutable[path] = digest
        assert sha(envelope['source_acceptance']) == envelope['source_acceptance_sha256']
        immutable[envelope['source_acceptance']] = envelope['source_acceptance_sha256']
        name = 'templates/'+item['run_id']+'.envelope.json'
        save(name, envelope)
        templates.append(dict(path=name, sha256=sha(OWN/name), run_id=item['run_id'],
            status=envelope['status'], spent=spent, launch_authority=False,
            control='Retains original spent dispatch; no successor target.' if spent else 'Inert successor source binding only.'))
    save('template-index.json', dict(launch_authority=False, approval_templates_created=0,
        source_origin=str(OWN), fresh_parent_review_required=True, envelopes=templates))
    save('source-pins.json', dict(source_origin=str(OWN), reviewed_origin=str(BASE),
        reviewed_manifest_sha256=BASE_SHA, manifest_sha256=sha(OWN/'source-manifest.json'),
        source_files=read(OWN/'source-manifest.json')['files'], accepted_manifests=accepted,
        registrations=index['registrations'], immutable_metadata_and_source_pins=immutable,
        payload_limit='No checkpoint, performance table, resource journal or model payload read; no installed dependency requalification.'))
    save('preservation-before.json', dict(roots=[str(p) for p in roots],
        metadata=metadata(roots), immutable_pins=immutable,
        scope='Byte pins for named source/identity/failure metadata only; stat-only preservation of trees, including checkpoint/partial metrics. No payload opens there.'))
    print(json.dumps(dict(prepared=True, original_controls=25, added=4, inert_envelopes=6)))


def finalize():
    before = read(OWN/'preservation-before.json')
    after = metadata([Path(p) for p in before['roots']])
    drift = [p for p in set(after) | set(before['metadata']) if after.get(p) != before['metadata'].get(p)]
    byte_drift = [p for p, digest in before['immutable_pins'].items() if sha(p) != digest]
    save('preservation-after.json', dict(metadata_entries=len(after), metadata_drift=drift,
        named_byte_pins_checked=len(before['immutable_pins']), byte_drift=byte_drift,
        checkpoint_payloads_opened=False, performance_tables_read=False,
        owned_cache_empty=not list((OWN/'empty-cache').iterdir()),
        owned_dispatch_absent=not (OWN/'dispatch').exists(),
        scope='Metadata stability and named source/identity/failure hashes; not checkpoint payload rehash or dependency/runtime qualification.'))
    assert not drift and not byte_drift
    for name, digest in read(OWN/'source-manifest.json')['files'].items():
        assert sha(OWN/name) == digest
    suites = {name: read(OWN/path) for name, path in (
        ('fake', 'validation/fake/test-receipt.json'),
        ('original_real', 'validation/real/real-test-receipt.json'),
        ('ps_boundary', 'validation/ps/ps-test-receipt.json'))}
    for name, count in (('fake', 11), ('original_real', 14), ('ps_boundary', 4)):
        result = suites[name]
        assert result['tests_run'] == count and result['successful']
        assert result['failures'] == result['errors'] == result['raw_exit'] == 0
        assert result['forbidden_runtime_imports'] == []
        assert result.get('remaining_owned_handles', []) == []
    assert not list((OWN/'empty-cache').iterdir()) and not (OWN/'dispatch').exists()
    save('receipt.json', dict(schema='progressive1000_ps_timeout_source_preparation_receipt_v6',
        status='source_prepared_pending_fresh_parent_review', source_origin=str(OWN),
        source_manifest_sha256=sha(OWN/'source-manifest.json'),
        exact_diff_sha256=sha(OWN/'exact-input-diff.patch'),
        controls=dict(original_retained=25, added=4, total=29,
            fake=11, original_real=14, new_real_boundary=4, failures=0, errors=0,
            elapsed_seconds={name: value['elapsed_seconds'] for name, value in suites.items()}),
        unchanged_registered_limits=dict(work_seconds=1790, total_seconds=1800, cleanup_seconds=10, retries=0),
        immutable_drift=0, actual_campaign_launches=0, inert_envelopes=6,
        spent_registration=dict(run_id=SPENT, status='closed_no_retry', renamed=False,
            successor_dispatch_target_provided=False, launch_approval_created=False),
        remaining_five='Unlaunched; inert templates confer no authority.',
        fresh_parent_review_required=True, training_eligible=False, promoted=False,
        evidence_limits=[
            'Real bounded stdlib controls with synthetic gates and shortened test clocks; no training/runtime/checkpoint qualification.',
            'No new restore probe, model import, campaign, retry, registration, approval, lease or marker operation.',
            'Partial checkpoints12/24/36 and metrics preserved by no writes and stable metadata; checkpoint payloads not read.',
            'Actual run has no terminal60 endpoint or comparison acceptance.',
            'Inherited filesystem/fsync and OS scheduling limits remain; no new hard real-time guarantee.']))
    save('artifact-manifest.json', dict(schema='owned_source_and_evidence_artifact_manifest_v1',
        files={str(p.relative_to(OWN)): sha(p) for p in sorted(OWN.rglob('*')) if p.is_file()},
        scope='Every regular owned artifact except this self-manifest; includes retained synthetic failures/staging files.'))
    print(json.dumps(dict(status='prepared_pending_parent_review', controls=29, drift=0,
        source_manifest_sha256=sha(OWN/'source-manifest.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'finalize'])
    args = parser.parse_args()
    prepare() if args.phase == 'prepare' else finalize()
