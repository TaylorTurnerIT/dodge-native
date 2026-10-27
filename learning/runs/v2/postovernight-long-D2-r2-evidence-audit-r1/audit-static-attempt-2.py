#!/usr/bin/env python3
"""Independent read-only audit of retained r2 preparation evidence. Stdlib only."""
from pathlib import Path
from collections import Counter
import ast
import hashlib
import json
import re
import signal

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
BASE = ROOT / 'learning/runs/v2/postovernight-long-D2-prepare-r2'
OLD = BASE.parent / 'postovernight-long-D2-prepare-r1'
OUT = BASE.parent / 'postovernight-long-D2-r2-evidence-audit-r1'
INPUTS = {}


def digest(path):
    path = Path(path)
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    INPUTS[str(path)] = value
    return value


def read(path):
    digest(path)
    return json.loads(Path(path).read_bytes())


def text(path):
    digest(path)
    return Path(path).read_text()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def nodes(path):
    source = text(path)
    lines = source.splitlines(keepends=True)
    return {node.name: ''.join(lines[min([node.lineno] + [d.lineno for d in node.decorator_list])-1:node.end_lineno])
            for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def assert_log(path):
    value = text(path)
    assert 'FAIL:' in value and 'AssertionError' in value, str(path)
    assert not re.search(r'^ERROR:', value, re.M), str(path)
    assert not any(x in value for x in ('ImportError:', 'SyntaxError:', 'AttributeError:', 'TypeError:')), str(path)
    return dict(assertion_failures=len(re.findall(r'^FAIL:', value, re.M)), no_API_or_import_errors=True)


def main():
    implementation = read(BASE / 'implementation-result.json')
    assert digest(BASE/'long_d2.py') == '0fe9970187e5c4c2576ff2929a475025cd5731a538325ffac78f172304af1d01'
    assert digest(BASE/'long-identity.json') == '969d825968e7782bc377cfd4d9312cf186df351e5219bff64d849f3d79781ed0'
    capsule = BASE/'capsule-final'
    assert digest(capsule/'capsule-manifest.json') == 'b1ccbeefe219c24f33b34db19178f4af68baa9674a058b066738231282ef25a1'
    artifacts = read(BASE/'artifact-manifest-final.json')['files']
    for name, expected in artifacts.items():
        assert digest(BASE/name) == expected, name
    actual = {str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file()}
    assert actual == set(artifacts) | {'artifact-manifest-final.json'}
    protected = read(BASE/'protected-before.json')
    assert protected == read(BASE/'protected-after.json')
    mutable_ledger = 'learning/runs/v2-orchestration/state.json'
    for name, expected in protected.items():
        if name == mutable_ledger:
            assert digest(BASE/'ledger-observation-before.json') == expected
            assert digest(BASE/'ledger-observation-after.json') == expected
        else:
            assert digest(ROOT/name) == expected, name

    identity = read(BASE/'long-identity.json')
    manifest = read(capsule/'capsule-manifest.json')['files']
    for name, expected in manifest.items():
        path = capsule/name
        assert digest(path) == expected
        assert not path.stat().st_mode & 0o222
    for directory in [capsule, *(p for p in capsule.rglob('*') if p.is_dir())]:
        assert not directory.stat().st_mode & 0o222
    assert {str(p.relative_to(capsule)) for p in capsule.rglob('*') if p.is_file()} == set(manifest) | {'capsule-manifest.json'}
    active_sources = {str(p.relative_to(ROOT)): digest(p) for p in BASE.glob('*.py')}
    assert identity['controller_sources'] == active_sources
    for name, expected in active_sources.items():
        assert manifest[name] == expected
    for name, expected in identity['base_registered_identity']['sources'].items():
        assert digest(ROOT/name) == digest(capsule/name) == expected
    assert len(identity['base_registered_identity']['sources']) == 75
    for name, expected in identity['original_input_pins'].items():
        assert digest(name) == expected
    semantic = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    assert semantic == implementation['checkpoint_identity_semantic_sha256']
    assert semantic != digest(BASE/'long-identity.json')
    assert all(not name.startswith('learning/runs/v2/postovernight-long-D2-prepare-r1/') for name in manifest)
    assert 'learning/runs/v2/postovernight-long-D2-prepare-r2/long-identity.json' in manifest

    source_before, source_after = nodes(OLD/'long_d2.py'), nodes(BASE/'long_d2.py')
    changed = sorted(name for name in source_before if source_after.get(name) != source_before[name])
    assert changed == sorted(('capsule_context','cancellation_signals','Guard','absolute_alarm','publish_terminal','supervise','worker'))
    for name in ('Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control'):
        assert source_before[name] == source_after[name]
    expected_worker = source_before['worker'].replace('                  worker_wall_seconds_lower_bound=',
        "                  inherited_consumed_wall_scope='D1 historical context only; long budget uses supervisor T0',\n                  worker_wall_seconds_lower_bound=")
    assert expected_worker == source_after['worker']

    methods = set()
    for name in ('test_long_d2.py','test_publication.py'):
        tree = ast.parse(text(BASE/name))
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef):
                for node in cls.body:
                    if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                        methods.add(f'{Path(name).stem}.{cls.name}.{node.name}')
    final_log = text(BASE/'tests-final-r6.log')
    logged = re.findall(r'^test_\w+ \(([\w.]+)\) \.\.\. ok$', final_log, re.M)
    assert len(logged) == len(set(logged)) == len(methods) == 83
    assert set(logged) == methods
    assert re.search(r'Ran 83 tests in 19\.803s\n\nOK\s*$', final_log)
    test_receipt = read(BASE/'test-receipt.json')
    assert digest(BASE/'tests-final-r6.log') == test_receipt['log_sha256']

    negative = read(BASE/'negative-control-receipt-final5.json')
    source = text(BASE/'long_d2.py')
    negative_results = []
    assert len(negative['cases']) == 14
    for case in negative['cases']:
        expected = source.replace(case['original_fragment'], case['broken_fragment'])
        assert source.count(case['original_fragment']) == case['replacements']
        assert text(BASE/case['source']) == expected
        assert digest(BASE/case['source']) == case['source_sha256']
        assert digest(BASE/case['log']) == case['log_sha256']
        negative_results.append(dict(name=case['name'], **assert_log(BASE/case['log'])))
    exact = read(BASE/'r1-regression-control-receipt-final5.json')
    exact_results = []
    for case in exact['cases']:
        assert Path(case['source']) == OLD/'long_d2.py'
        assert digest(case['source']) == case['source_sha256'] == '62ece46ba9a59d3c116013580ce29875aa76eaceed59eb56480a804649c8ffca'
        assert digest(BASE/case['log']) == case['log_sha256']
        exact_results.append(dict(test=case['test'], **assert_log(BASE/case['log'])))
    preclosure = read(BASE/'preclosure-regression-control-receipt.json')
    assert digest(preclosure['source']) == preclosure['source_sha256']
    assert digest(BASE/preclosure['log']) == preclosure['log_sha256']
    preclosure_result = assert_log(BASE/preclosure['log'])

    cases = read(BASE/'publication-probe-receipt.json')['cases']
    actual_paths = {str(p.relative_to(BASE)) for p in (BASE/'publication-final-evidence-r6').glob('*/scenario/observation.json')}
    assert len(cases) == len(actual_paths) == len({c['path'] for c in cases}) == 66
    assert {c['path'] for c in cases} == actual_paths
    unique_scenarios = set()
    counts = Counter()
    owned_groups = []
    signal_cases = []
    for case in cases:
        path = BASE/case['path'];ob = read(path)
        assert digest(path) == case['sha256']
        assert ob['controller_sha256'] == implementation['controller_sha256']
        assert ob['actual_supervise'] and ob['actual_guard'] and ob['owned_stdlib_OS_worker']
        assert ob['trigger_fired'] and not ob['ML_imports']
        assert ob['owned_group_positively_absent'] and ob['manifest_still_matches']
        assert all(not entry['open_output_writers'] for entry in ob['artifact_hash_writer_checks'])
        parent=path.parent.parent
        raw=read(parent/'subprocess-receipt.json')
        assert raw['return_code'] == ob['return_code']
        assert Path(raw['argv'][2]) == BASE/'publication_probes.py'
        for key in ('mode','mutation','phase','return_code','manifest_available','controller_sha256'):
            assert case[key] == ob[key]
        if ob['mutation'] != 'none':
            assert ob['return_code'] == 1 and ob['terminal']['experiment_status'] == 'failed' and not ob['manifest_available']
        else:
            assert ob['return_code'] == (0 if ob['mode']=='pass' else 2)
            assert ob['terminal']['experiment_status'] == 'complete' and ob['manifest_available']
            assert any(v['live_memory_monitor'] for v in ob['artifact_hash_writer_checks'])
            resource=ob['terminal']['supervisor_resources_final']
            assert resource['maximum_sample_gap_seconds'] <= .5 and resource['maximum_full_input_gap_seconds'] <= 5
            manifest_path=path.parent/'campaign/artifact-manifest.json'
            stable=read(manifest_path)
            for name, expected in stable.items():assert digest(manifest_path.parent/name)==expected
            assert digest(manifest_path)==ob['terminal']['artifact_manifest_sha256']
            assert digest(manifest_path.parent/'long-run-result.json')==ob['terminal']['run_result_sha256']
        if ob['mutation'] in ('SIGINT','SIGTERM'):
            event=next(e for e in ob['events'] if e['event']=='real_signal')
            assert event['number'] == getattr(signal,ob['mutation'])
            signal_cases.append(dict(phase=ob['phase'],signal=ob['mutation'],mode=ob['mode'],handler=event['handler']))
        stops=[e['receipt'] for e in ob['events'] if e['event']=='owned_stop']
        assert len(stops)==1 and stops[0]['reaped'] and stops[0]['group_empty']
        owned_groups.append(stops[0]['owned_pgid'])
        unique_scenarios.add((ob['phase'],ob['mutation'],ob['mode'],ob['delay_seconds']))
        counts[ob['mutation']] += 1
    assert len(set(owned_groups))==66
    assert len(unique_scenarios)==66
    summary = dict(status='passed_retained_evidence_and_static_coverage_only',
        artifact_files_verified=len(artifacts),immutable_protected_files_currently_verified=len(protected)-1,
        historical_mutable_ledger_verified_against_both_repair_observations=True,
        capsule_files_verified=len(manifest),active_execution_helper_test_python_files=len(active_sources),
        original_legacy_inputs_verified=75,positive_test_methods=83,original_methods=70,new_publication_methods=13,
        actual_Guard_owned_OS_probe_invocations=66,unique_probe_observation_paths=66,
        probe_mutation_counts=dict(counts),real_signal_probe_invocations=len(signal_cases),
        negative_controls=negative_results,exact_r1_regression_groups=exact_results,
        retained_preclosure_control=preclosure_result,
        learner_schedule_environment_counter_control_nodes_byte_identical=True,worker_only_change='Inherited wall-scope receipt label',
        changed_top_level_nodes=changed,identity_semantic_sha256=semantic,
        no_ML_or_project_import_or_campaign_execution=True,
        evidence_denominators='83 unittest methods include the 13 publication methods; 66 subprocess probes are their subtest executions and are not 66 additional methods.')
    write('verification.json', summary)
    write('input-sha256-manifest.json',dict(files=INPUTS))
    print(json.dumps({k:v for k,v in summary.items() if not isinstance(v,list)},indent=2))


if __name__=='__main__':main()
