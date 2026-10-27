"""Synthetic terminal files exercise production checks without game or checkpoint imports."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import auditor

V2 = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('statistics_test_fixture', V2 / 'confirmation-bootstrap-parent-repair-20261026-r3/test_adapter.py')
import sys
sys.path.insert(0, str(Path(SPEC.origin).parent))
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + '\n')
    return digest(path)


def fixture(directory, difference=1):
    base = Path(directory)
    outputs = base / 'outputs'
    outputs.mkdir()
    cache = base / 'empty-pycache'
    cache.mkdir()
    arguments = FIXTURE.fixture(difference)
    reg = json.loads(arguments['registration_bytes'])
    reg.update({'output_dir': str(outputs), 'one_shot_marker': str(base / 'claimed'),
                'cancel_path': str(base / 'CANCEL'), 'state_path': str(base / 'state.json'),
                'expected_lease': {'run_id': reg['run_id'], 'owner_token': 'toy-only'},
                'limits': {'outer_seconds': 5977}})
    source = base / 'source.py'
    source.write_text('# synthetic immutable source\n')
    reg['source'] = {key: value for name in ('launcher', 'worker', 'evaluator')
                     for key, value in ((name + '_path', str(source)), (name + '_sha256', digest(source)))}
    runtime = base / 'runtime'
    runtime.mkdir()
    members = {}
    for index in range(13):
        member = runtime / str(index)
        member.write_bytes(b'synthetic runtime member')
        members[member.name] = digest(member)
    reg['runtime'].update(root=str(runtime), member_sha256=members, pycache_prefix=str(cache))
    # This is the public frozen seed manifest, never an episode-outcome artifact.
    manifest = V2 / 'expanded-evaluation-registration-proposal-parent-20261026-r5/confirmation-seed-manifest.json'
    for name in ('confirmation', 'ranking', 'benchmark_dev64'):
        reg['cohorts'][name] = {'manifest_path': str(manifest), 'manifest_sha256': digest(manifest), 'count': 2048}
    candidates = reg['candidates']
    for update in (180, 204, 276, 300, 324, 348):
        checkpoint = base / f'checkpoint-{update}'
        checkpoint.write_bytes(b'synthetic checkpoint bytes; never deserialize')
        receipt = base / f'candidate-receipt-{update}.json'
        write(receipt, {'synthetic': True})
        candidates.setdefault(str(update), {})
        candidates[str(update)].update(checkpoint_path=str(checkpoint), checkpoint_sha256=digest(checkpoint),
                                       source_receipt_path=str(receipt), source_receipt_sha256=digest(receipt))
    # An opaque fixture stands in for the frozen incumbent. Success tests mock only its digest oracle;
    # no test attempts to manufacture a SHA-256 preimage or read a production checkpoint.
    selection = json.loads(arguments['selection_bytes'])
    selection['winner_checkpoint_sha256'] = candidates['324']['checkpoint_sha256']
    candidates['348']['checkpoint_sha256'] = FIXTURE.adapter.INCUMBENT
    Path(candidates['348']['checkpoint_path']).write_bytes(b'synthetic incumbent checkpoint; never deserialize')
    selection_path = base / 'selection.json'
    reg['selection_record'].update(path=str(selection_path), sha256=write(selection_path, selection),
                                   winner_checkpoint_sha256=selection['winner_checkpoint_sha256'])
    adapter = V2 / 'confirmation-bootstrap-parent-repair-20261026-r3/adapter.py'
    reg['review_records'] = [{'kind': 'confirmation_statistics_adapter', 'path': str(adapter), 'sha256': digest(adapter)},
                             {'kind': 'runtime_executable', 'path': sys.executable, 'sha256': digest(sys.executable)}]
    benchmark_worker = base / 'benchmark-worker.json'
    benchmark_outer = base / 'benchmark-outer.json'
    write(benchmark_worker, {'complete': True})
    write(benchmark_outer, {'raw_exit_code': 0, 'stop_reason': None, 'process_group_absent': True})
    benchmark = base / 'accepted-benchmark.json'
    write(benchmark, {'schema': 'expanded_eval_accepted_benchmark_evidence_v1', 'complete': True,
                      'worker_receipt_path': str(benchmark_worker), 'worker_receipt_sha256': digest(benchmark_worker),
                      'outer_receipt_path': str(benchmark_outer), 'outer_receipt_sha256': digest(benchmark_outer)})
    reg['benchmark_measurement'] = {'receipt_path': str(benchmark), 'receipt_sha256': digest(benchmark)}
    reg['provenance'] = {'root_readme': {'path': str(V2.parents[2] / 'README.md'),
                                         'sha256': 'be478416b33c772a7ff9c28f2c974f767c205f7df77bcf7346ab36133d384652'}}
    reg_path = base / 'registration.json'
    reg_sha = write(reg_path, reg)
    write(Path(reg['state_path']), {'active_inference_diagnostic': reg['expected_lease']})
    write(Path(reg['one_shot_marker']), {'run_id': reg['run_id'], 'registration_sha256': reg_sha, 'pid': 800001})
    heartbeat = outputs / 'worker-heartbeat.json'
    write(heartbeat, {'run_id': reg['run_id'], 'registration_sha256': reg_sha, 'pid': 800002,
                       'rss_bytes': 1024, 'mps_driver_bytes': 1024, 'phase': 'runtime', 'driver_initialized': True})
    results = []
    paths = []
    for name, key in (('confirmation-winner.json', 'winner'), ('confirmation-incumbent-348.json', 'incumbent')):
        result = json.loads(arguments[key + '_bytes'])
        result['registration_sha256'] = reg_sha
        result['checkpoint_sha256'] = candidates[str(result['candidate_update'])]['checkpoint_sha256']
        value = result['rows'][0]['alive_frames']
        result['performance'] = dict.fromkeys(('worst', 'q1_bottom_quarter_mean', 'mean', 'q4_top_quarter_mean', 'best'), value)
        result['elapsed_seconds'] = 1.0
        path = outputs / name
        write(path, result)
        results.append(result)
        paths.append(path)
    summary = outputs / 'confirmation.json'
    write(summary, {'schema': 'expanded_D2_stage_bundle_v1', 'stage': 'confirmation', 'results': results})
    paths += [summary, heartbeat]
    outer = outputs / 'confirmation.json.outer-receipt.json'
    write(outer, {'schema': 'expanded_eval_outer_receipt_v1', 'run_id': reg['run_id'], 'registration_sha256': reg_sha,
                  'stage': 'confirmation', 'candidate_update': 324, 'cohort': 'confirmation', 'raw_exit_code': 0,
                  'stop_reason': None, 'elapsed_seconds': 3.0, 'process_group_absent': True, 'process_group_remaining': [],
                  'worker_sha256': reg['source']['worker_sha256'], 'evaluator_sha256': reg['source']['evaluator_sha256'],
                  'output_artifacts': [{'path': str(p), 'sha256': digest(p), 'bytes': p.stat().st_size} for p in paths]})
    return reg_path, reg_sha, outer, outputs, reg


class IntegratedTests(unittest.TestCase):
    def test_success_and_inconclusive_use_real_statistics_and_preserve_existing_receipts(self):
        for difference, expected in ((1, 'eligible'), (0, 'inconclusive')):
            with self.subTest(difference=difference), tempfile.TemporaryDirectory() as directory:
                registration, pin, _, _, _ = fixture(directory, difference)
                original = auditor.sha

                def fixture_digest(data):
                    if data == b'synthetic incumbent checkpoint; never deserialize':
                        return FIXTURE.adapter.INCUMBENT
                    return original(data)

                destination = Path(directory) / 'receipts'
                with patch.object(auditor, 'sha', fixture_digest):
                    result = auditor.audit(registration, pin, 0, destination, ps_runner=lambda _: '')
                    self.assertEqual(result['eligibility'], expected)
                    self.assertFalse(result['promotion'])
                    saved = (destination / 'receipt.json').read_bytes()
                    with self.assertRaisesRegex(auditor.AuditError, 'already exists'):
                        auditor.audit(registration, pin, 0, destination, ps_runner=lambda _: '')
                    self.assertEqual((destination / 'receipt.json').read_bytes(), saved)

    def test_production_pin_checks_reject_fixture_incumbent_identity_before_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            registration, pin, _, _, _ = fixture(directory)
            with self.assertRaisesRegex(auditor.AuditError, 'checkpoint SHA-256 mismatch'):
                auditor.audit(registration, pin, 0, Path(directory) / 'receipts', ps_runner=lambda _: '')

    def test_missing_outer_result_binding_rejected_before_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            registration, pin, outer, _, _ = fixture(directory)
            record = json.loads(outer.read_bytes())
            record['output_artifacts'].pop(0)
            write(outer, record)
            with self.assertRaisesRegex(auditor.AuditError, 'required outcome bindings'):
                auditor.audit(registration, pin, 0, Path(directory) / 'receipts', ps_runner=lambda _: '')

    def test_remaining_process_rejected_before_any_quality_json_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            registration, pin, _, _, _ = fixture(directory)
            original = json.loads

            def reject_quality(data, *args, **kwargs):
                value = original(data, *args, **kwargs)
                if isinstance(value, dict) and ('rows' in value or 'results' in value):
                    self.fail('quality decoded before process absence passed')
                return value

            with patch.object(auditor.json, 'loads', reject_quality):
                with self.assertRaisesRegex(auditor.AuditError, 'process remains'):
                    auditor.audit(registration, pin, 0, Path(directory) / 'receipts', ps_runner=lambda _: '800002 1 800002')


if __name__ == '__main__':
    unittest.main()
