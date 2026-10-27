"""Summarize existing finite unit evidence and recheck read-only input hashes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

OUT = Path(__file__).resolve().parent

def read(name):
    return json.loads((OUT / name).read_text())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

inputs, first, repair = read('inputs.json'), read('invocation.json'), read('repair-invocation.json')
parity, integration = read('results/parity-comparison.json'), read('results/integration-summary.json')
binding, fake = read('results/binding-controls.json'), read('results/fake-controls-repaired.json')
assert parity['all_exact'] and integration['complete'] and binding['success'] and fake['success']
assert binding['tests_run'] == 8 and fake['tests_run'] == 41
assert repair['complete'] and repair['aggregate_child_wall_seconds'] < 300
assert all(r['group_absent'] and r['wall_seconds'] < 120 for r in first['commands'])
assert repair['group_absent'] and repair['wall_seconds'] < 120
assert all(sha(path) == expected for path, expected in inputs['pins'].items())
assert all(sha(OUT / path) == expected for path, expected in inputs['copied_sources'].items())
assert all(sha(OUT / path) == expected for path, expected in first['source_hashes'].items())
frozen_ppo = OUT.parent / 'D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/ppo.py'
additional = {str(frozen_ppo): {'sha256': sha(frozen_ppo),
    'reason': 'read-only Python-source baseline imported by exact inherited fake control',
    'limit': 'post-run source hash, not an initial baseline; no checkpoint read'}}
summary = []
for name in ('enabled_full256', 'disabled_full256', 'enabled_split128_128', 'enabled_post_reset_guard_failure'):
    row = read('results/' + name + '.json')
    snapshot = row['snapshot']
    summary.append({'name': name, 'complete': row['complete'], 'native_vector_steps': row['native_steps'],
        'cutoff_survivors': sum(len(r['indices']) for r in row['native_cutoffs']),
        'death_boundaries': sum(sum(r.get('terminated', [])) for r in row['step_evidence']),
        'gameplay_frames_including_fatal': snapshot['gameplay_frames_including_fatal'],
        'accepted_reset_count': snapshot['normal_reset_count'],
        'actual_combined_subset_reset_calls': len(row['combined_resets']),
        'returned_reset_startup_frames': snapshot['returned_reset_startup_frames_unaudited'],
        'accepted_reset_startup_frames': snapshot['reset_startup_frames'],
        'gae': row.get('gae'), 'actual_native_optimizer_steps': row['optimizer_steps'],
        'scheduler_completed_updates': snapshot['completed_updates'],
        'scheduler_pending_update': snapshot['pending_update'],
        'decision255_observed': 'decision255' in row,
        'native_boundary_at_decision255': False if 'decision255' in row else None,
        'expected_negative_control': row['expected_failure']})
source_manifest = {'schema': 'owned_python_integration_source_manifest_v1',
    'files': {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob('*.py'))},
    'exact_collector_source_manifest_sha256': inputs['pins'][str(Path(inputs['collector']) / 'source-manifest.json')],
    'native_binaries_copied_or_installed': False, 'accepted_sources_modified': False,
    'repair': 'repairs/control-import-r1.diff'}
write('source-manifest.json', source_manifest)
receipt = {'schema': 'native_collector_finite_cpu_integration_receipt_v1',
    'at_utc': datetime.now(timezone.utc).isoformat(), 'owned_output': str(OUT),
    'status': 'finite_cpu_unit_validation_passed_after_owned_harness_import_repair',
    'input_pins': inputs['pins'], 'additional_read_only_source': additional,
    'source_manifest_sha256': sha(OUT / 'source-manifest.json'),
    'native_disabled_cutoff_parity': parity, 'actual_native_integration': summary,
    'same_new_binary_for_enabled_disabled': True,
    'full_vs_split128_128_batch_digest_exact': integration['split_full_batch_exact'],
    'controls': {'binding': {'inherited_exact_tests': 6, 'additional_actual_API_tests': 2, 'passed': 8},
        'fake_collector_scheduler': {'passed': 41,
            'limit': 'includes inherited fake-environment CPU optimizer/PPO contract units; these are not actual-native training'}},
    'first_failure': {'path': 'logs/first-failure.log', 'detail_log': 'logs/fake-controls.log',
        'cause': "ModuleNotFoundError: No module named 'scheduler_reference'",
        'classification': 'owned test harness import path; no collector/native integration bug observed',
        'before_failure': '20 fake collector tests passed, scheduler module import failed',
        'repair': 'repairs/control-import-r1/controls_driver.py', 'diff': 'repairs/control-import-r1.diff',
        'rerun': 'only affected fake-control suite; no parity/native/binding rerun'},
    'resources': {'aggregate_child_wall_seconds_including_failed_attempt_and_repair': repair['aggregate_child_wall_seconds'],
        'total_cap_seconds': 300, 'per_process_deadline_seconds': 120,
        'maximum_observed_child_wall_seconds': max([r['wall_seconds'] for r in first['commands']] + [repair['wall_seconds']]),
        'all_owned_child_groups_absent': True, 'commands': 'invocation.json', 'repair_command': 'repair-invocation.json'},
    'protected_input_postflight': {'all_64_listed_pins_match_initial': True,
        'exact_collector_copies_unchanged': True, 'initial_owned_unit_sources_unchanged': True,
        'limit': 'listed file verification and own-output writes only; no whole-workspace concurrent-write attribution'},
    'coverage_limits': [
        'Finite D1/D2 disabled-cutoff explicit-seed units only; no global old/new source-to-binary correspondence.',
        'Actual-native collector fixture is D1, normal starts, training run_seed777, batch8, one256-decision pending unit update; no D2 collector qualification.',
        'Seven real H1000 cutoffs at decision249; one death at gameplay631/decision157. No simultaneous native death/cutoff vector, death exactly on H, H2000, or ordinary18000 cap reached.',
        'Parity reached58 true deaths/resets per binary but zero512 caps. Binding controls reach an actual configured cap8; prior author Rust fixture claims were not rerun here.',
        'Decision255 continuation was reached. Decision255 boundary is covered only by inherited fake controls, not reached by this native fixture.',
        'Two128-decision buffers cover actual native continuation within one pending unit update. No successful PPO or real next-update transition is claimed.',
        'Scheduler remains update0/generation0 with pending_update1 in actual-native fixtures. Post-PPO ordering/promotion uses inherited fake controls only.',
        'Historical exclusion floor validated exactly; no exhaustive ancestry/future-cohort freshness, reservation or study seed proof.',
        'No forced production death, state mutation, frame jump, seed flag rewrite or accepted learner/checkpoint used.'
    ],
    'remaining_parent_gates': [
        'Independent native-source and integration-driver review and parent acceptance.',
        'Full successor runtime/build/model/evaluator/dependency identity and strict membership/restore bindings.',
        'Authenticated accepted checkpoint/model/Adam/RNG restore and independent backend references; outside this lane.',
        'Exhaustive ancestry/future seed exclusions, fresh parent-owned vectors/cohorts and preserved slot offsets.',
        'Resource/cleanup calibration, aggregate ceilings, durable registration, leases/markers and explicit launch authority.'
    ],
    'authority': {'runtime_qualified': False, 'training_qualified': False,
        'global_binary_correspondence_proven': False, 'launch_authority': False,
        'checkpoint_read_or_deserialized': False, 'accepted_model_loaded': False,
        'MPS': False, 'study_or_B_E_cohorts_used': False,
        'training_or_evaluation_campaign': False, 'commits_or_pushes': False,
        'subdelegation': False, 'extension_install_or_overwrite': False}}
write('receipt.json', receipt)
artifact_manifest = {'schema': 'owned_integration_artifacts_sha256_v1',
    'files': {str(p.relative_to(OUT)): {'sha256': sha(p), 'bytes': p.stat().st_size}
              for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'artifact-manifest.json'}}
write('artifact-manifest.json', artifact_manifest)
print(json.dumps({'status': receipt['status'], 'owned': str(OUT),
    'aggregate_child_wall_seconds': repair['aggregate_child_wall_seconds'],
    'artifact_files': len(artifact_manifest['files']), 'protected_pins_verified': len(inputs['pins'])}))
