"""Preparation-only receipts and candidate capsule; never launch the diagnostic."""
import hashlib
import json
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PROTOCOL = ROOT / 'learning/runs/v2-orchestration/postovernight-action-mode-r3-protocol.json'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(p, x):
    with p.open('x') as f:
        json.dump(x, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')

started = time.monotonic()
p = json.loads(PROTOCOL.read_text())
assert not (ROOT / p['output']).exists(), 'Preparation must not touch the campaign output'
initial = {str(PROTOCOL): sha(PROTOCOL)}
files = dict(p['foundation_sources'])
files[p['foundation_identity_path']] = p['foundation_identity_sha256']
files[str(PROTOCOL.relative_to(ROOT))] = sha(PROTOCOL)
for item in p['checkpoints']:
    files[item['path']] = item['sha256']
    if item['control']:
        files[item['control']] = item['control_sha256']
for name in ('runner.py', 'test_harness.py', 'test_finalization.py', 'prepare_receipts.py'):
    files[str((HERE / name).relative_to(ROOT))] = sha(HERE / name)
for name, digest in files.items():
    assert sha(ROOT / name) == digest, name
initial.update({str(ROOT / name): digest for name, digest in files.items()})
foundation = json.loads((ROOT / p['foundation_identity_path']).read_text())
for name, digest in foundation['foundation']['binary_and_receipt_sha256'].items():
    assert sha(name) == digest, name
    initial[name] = digest

source_hashes = {name: sha(HERE / name) for name in
                 ('runner.py', 'test_harness.py', 'test_finalization.py', 'prepare_receipts.py')}
command = [str(ROOT / 'python/.venv/bin/python'), '-B', str(HERE / 'test_harness.py')]
commands = [command, [command[0], '-B', str(HERE / 'test_finalization.py')]]
test_start = time.monotonic()
rounds = []
with (HERE / 'tests-final.log').open('x') as stream:
    for test_command in commands:
        completed = subprocess.run(test_command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=60)
        rounds.append({'command': test_command, 'exit_code': completed.returncode})
        assert completed.returncode == 0, 'Final synthetic validation failed; log retained'
test_wall = time.monotonic() - test_start
log = (HERE / 'tests-final.log').read_text()
matches = re.findall(r'Ran (\d+) tests in ([0-9.]+)s', log)
receipt = {'commands': rounds, 'cwd': str(ROOT), 'exit_code': 0,
           'execution_source_sha256': source_hashes,
           'test_count': sum(int(m[0]) for m in matches),
           'reported_seconds': sum(float(m[1]) for m in matches),
           'wall_seconds': test_wall, 'log_sha256': sha(HERE / 'tests-final.log'),
           'original_regressions': 44, 'new_finalization_regressions': 28,
           'scope': 'Standalone synthetic/pure CPU tests, fake tiny policies/environments, mocked probes, fixture leases, real bounded dummy subprocesses. Dodge imports are forbidden by an import guard. New finalization cases call actual supervise with fake worker/clock/guard and real fixture persistence. No actual teacher/native/model/MPS inference, no production campaign, no training.',
           'historical_test_counts_used': False}
write(HERE / 'test-receipt.json', receipt)
assert receipt['test_count'] == 72

frozen = ROOT / 'learning/runs/v2/postovernight-action-mode-prepare-r1/source-snapshot/learning/runs/v2/postovernight-action-mode-prepare-r1/runner.py'
assert sha(frozen) == '6159ba14637274a56b5324bb195b6f02ef35de5a6e760ee78d628aa95b991e2d'
archive = HERE / 'negative-control-source'
archive.mkdir()
for name in ('runner.py', 'test_harness.py', 'prepare_receipts.py'):
    source = frozen.with_name(name)
    shutil.copyfile(source, archive / name)
    (archive / name).chmod(0o444)
selected = [
 'test_late_guard_close_fails', 'test_late_final_verification_fails',
 'test_late_output_hash_fails', 'test_late_serialization_fails',
 'test_late_manifest_publication_fails',
 'test_reaped_nonempty_group_suppresses_manifest',
 'test_reaped_missing_group_proof_suppresses_manifest',
 'test_reaped_group_probe_error_suppresses_manifest',
 'test_reaped_group_probe_errors_suppress_manifest',
 'test_unreaped_leader_suppresses_manifest',
 'test_cleanup_reserve_cannot_buy_normal_finalization',
 'test_cleanup_over_10_seconds_fails_even_before_deadline']
negative_command = [command[0], '-B', str(HERE / 'test_finalization.py')] + [
    'FinalizationTests.' + name for name in selected]
with (HERE / 'negative-controls.log').open('x') as stream:
    negative = subprocess.run(negative_command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', FINALIZATION_RUNNER=str(frozen)), timeout=60)
negative_log = (HERE / 'negative-controls.log').read_text()
assert negative.returncode == 1 and 'FAILED (failures=12)' in negative_log
assert 'ERROR:' not in negative_log and negative_log.count('AssertionError:') == 12
negative_receipt = {'command': negative_command, 'cwd': str(ROOT),
    'environment': {'PYTHONDONTWRITEBYTECODE': '1', 'FINALIZATION_RUNNER': str(frozen)},
    'exit_code': negative.returncode, 'semantic_assertion_failures': 12, 'errors': 0,
    'selected_tests': selected, 'target_sha256': sha(frozen),
    'test_source_sha256': source_hashes['test_finalization.py'],
    'log_sha256': sha(HERE / 'negative-controls.log'),
    'archive_files': {name: sha(archive / name) for name in ('runner.py', 'test_harness.py', 'prepare_receipts.py')},
    'fixture_isolation': 'Same fixture, actual supervise, exact frozen r1 imported unmodified; fixture protocol/lease paths and hashes injected equally for r1/r2. No API/import/protocol path failures count as evidence.'}
write(HERE / 'negative-control-receipt.json', negative_receipt)

frozen_r2 = ROOT / 'learning/runs/v2/postovernight-action-mode-prepare-r2/source-snapshot/learning/runs/v2/postovernight-action-mode-prepare-r2/runner.py'
assert sha(frozen_r2) == '6c190542e142d34f12466d9ad17cfa8867b72111defc58517a37c068561d9dd4'
archive_r2 = HERE / 'negative-control-r2-source'
archive_r2.mkdir()
for name in ('runner.py', 'test_harness.py', 'test_finalization.py', 'prepare_receipts.py'):
    shutil.copyfile(frozen_r2.with_name(name), archive_r2 / name)
    (archive_r2 / name).chmod(0o444)
selected_r2 = [
    'test_SIGINT_during_cleanup_fails', 'test_SIGTERM_during_cleanup_fails',
    'test_SIGINT_during_guard_close_fails', 'test_SIGTERM_during_guard_close_fails',
    'test_SIGINT_during_final_verification_fails', 'test_SIGTERM_during_final_verification_fails',
    'test_repeated_SIGINT_during_cleanup_latches_all', 'test_repeated_SIGTERM_during_cleanup_latches_all']
negative_r2_command = [command[0], '-B', str(HERE / 'test_finalization.py')] + [
    'FinalizationTests.' + name for name in selected_r2]
with (HERE / 'negative-controls-r2.log').open('x') as stream:
    negative_r2 = subprocess.run(negative_r2_command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', FINALIZATION_RUNNER=str(frozen_r2)), timeout=60)
negative_r2_log = (HERE / 'negative-controls-r2.log').read_text()
assert negative_r2.returncode == 1 and 'FAILED (failures=8)' in negative_r2_log
assert 'ERROR:' not in negative_r2_log and negative_r2_log.count('AssertionError:') == 8
negative_r2_receipt = {'command': negative_r2_command, 'cwd': str(ROOT),
    'environment': {'PYTHONDONTWRITEBYTECODE': '1', 'FINALIZATION_RUNNER': str(frozen_r2)},
    'exit_code': negative_r2.returncode, 'semantic_assertion_failures': 8, 'errors': 0,
    'selected_tests': selected_r2, 'target_sha256': sha(frozen_r2),
    'test_source_sha256': source_hashes['test_finalization.py'],
    'log_sha256': sha(HERE / 'negative-controls-r2.log'),
    'archive_files': {name: sha(archive_r2 / name) for name in ('runner.py', 'test_harness.py', 'test_finalization.py', 'prepare_receipts.py')},
    'fixture_isolation': 'Same actual supervise fixture and synthetic handler callbacks against exact frozen r2; no real OS signal, worker, model or API/setup error.'}
write(HERE / 'negative-control-r2-receipt.json', negative_r2_receipt)

write(HERE / 'test-manifest.json', {'version': 'r3_cancellation_test_manifest_v1',
    'execution_source_sha256': source_hashes, 'positive_test_count': 72,
    'original_regressions': 44, 'new_finalization_regressions': 28,
    'negative_control_semantic_assertion_failures': 12,
    'negative_control_r2_semantic_assertion_failures': 8,
    'negative_control_r2_receipt': str(HERE / 'negative-control-r2-receipt.json'),
    'commands': commands, 'negative_command': negative_command,
    'test_receipt_sha256': sha(HERE / 'test-receipt.json'),
    'negative_receipt_sha256': sha(HERE / 'negative-control-receipt.json'),
    'negative_r2_semantic_assertion_failures': 8, 'negative_r2_command': negative_r2_command,
    'negative_r2_receipt_sha256': sha(HERE / 'negative-control-r2-receipt.json')})
files[str((HERE / 'test-manifest.json').relative_to(ROOT))] = sha(HERE / 'test-manifest.json')
protected = json.loads((HERE / 'protected-before.json').read_text())
for name, digest in protected.items():
    assert sha(ROOT / name) == digest, f'Protected r1 evidence changed: {name}'
write(HERE / 'protected-after.json', {'files': protected, 'verified_count': len(protected),
      'all_byte_identical': True})
old_protocol = json.loads((ROOT / 'learning/runs/v2-orchestration/postovernight-action-mode-r1-protocol.json').read_text())
changed = {key: {'r1': old_protocol.get(key), 'r2': p.get(key)} for key in set(old_protocol) | set(p)
           if old_protocol.get(key) != p.get(key)}
assert set(changed) <= {'version', 'runner', 'protocol_revision', 'supersedes_protocol'}
write(HERE / 'protocol-revision-diff.json', {'changed_fields': changed,
      'experimental_settings_unchanged': True})

for name, digest in initial.items():
    assert sha(name) == digest, f'Input changed during preparation: {name}'

snapshot = HERE / 'source-snapshot'
snapshot.mkdir()
for name, digest in files.items():
    target = snapshot / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
    assert sha(target) == digest
    target.chmod(0o444)
manifest = {'version': 'action_mode_capsule_v1', 'files': files,
            'status': 'candidate_for_parent_review_not_execution_authorization',
            'external_pins': foundation['foundation']['binary_and_receipt_sha256']}
write(snapshot / 'capsule-manifest.json', manifest)
(snapshot / 'capsule-manifest.json').chmod(0o444)
for path in sorted((x for x in snapshot.rglob('*') if x.is_dir()), reverse=True):
    path.chmod(0o555)
snapshot.chmod(0o555)
capsule_hash = sha(snapshot / 'capsule-manifest.json')
write(HERE / 'source-manifest.json', {'files': files, 'file_count': len(files),
      'foundation_source_count': 75, 'source_snapshot': str(snapshot),
      'capsule_manifest_sha256': capsule_hash, 'execution_source_sha256': source_hashes,
      'original_input_checks_before_after': initial})

invocation = [str(ROOT / 'python/.venv/bin/python'), '-B', str(snapshot / p['runner']),
              '--protocol', str(PROTOCOL), '--output', str(ROOT / p['output']),
              '--state-path', str(ROOT / 'learning/runs/v2-orchestration/state.json')]
result = {
    'status': 'prepared_for_independent_parent_review',
    'runner': str(HERE / 'runner.py'), 'runner_sha256': source_hashes['runner.py'],
    'protocol': str(PROTOCOL), 'protocol_sha256': sha(PROTOCOL),
    'protocol_modified': False, 'source_snapshot': str(snapshot),
    'capsule_manifest_sha256': capsule_hash, 'parent_acceptance': 'pending',
    'test_receipt': str(HERE / 'test-receipt.json'), 'new_tests_passed': receipt['test_count'],
    'test_scope': receipt['scope'], 'test_commands': commands,
    'test_source_hashes': source_hashes,
    'accepted_findings_repaired': ['R1-F1', 'R1-F2', 'R2-F1'],
    'counter_repair': 'None; original worker counter-copy loop preserved and success/partial counts tested.',
    'cancellation_repair': 'Every signal request is latched and counted even while cleanup defers raising; supervisor checks retained latch after context exit before terminal publication.',
    'original_regressions_passed': 44, 'new_finalization_regressions_passed': 28,
    'negative_control_semantic_assertion_failures': 12,
    'negative_control_r2_semantic_assertion_failures': 8,
    'negative_control_r2_receipt': str(HERE / 'negative-control-r2-receipt.json'),
    'negative_control_receipt': str(HERE / 'negative-control-receipt.json'),
    'full_patch_vs_r1': str(HERE / 'full-patch-vs-r1.diff'),
    'protected_prior_evidence_count': len(protected), 'protected_prior_evidence_byte_identical': True,
    'protocol_revision_experiment_settings_unchanged': True,
    'terminal_publication': 'finalization-result.json is authoritative and binds the nonrecursive artifact manifest and run-result hash. Success requires exit 0; all normal stages use the original absolute deadline. Late failure removes candidate success manifest/terminal before publishing failed partial receipts. Unproven groups never hash mutable outputs.',
    'timing_scope': 'run-result prepublication_wall_seconds ends before its write. Authoritative finalization-result actual_total_wall_seconds includes result serialization, all artifact hashing, manifest publication/hash, and receipt preparation. It is explicitly a lower bound excluding its own write/process exit; a post-write check revokes late success. Parent observes actual process exit/wall. Cleanup is separately measured and cannot shift deadline.',
    'diagnostic_campaign_launched': False, 'campaign_output_exists': False,
    'actual_teacher_forwards': 0, 'actual_native_environments': 0,
    'actual_mps_inference_calls': 0, 'training_updates': 0, 'checkpoint_files_written': 0,
    'real_checkpoints_deserialized_during_preparation': 0,
    'production_ledger_or_metadata_writes': 0, 'existing_source_changes': 0,
    'qualification': False, 'training_eligibility_changed': False,
    'invocation_after_parent_review_only': invocation,
    'required_parent_lease': {
        'active_long_campaign': {
            'kind': 'M3_action_mode_diagnostic', 'authorization': 'new_postovernight_inference_only',
            'run_id': p['run_id'], 'protocol_sha256': sha(PROTOCOL),
            'harness_sha256': source_hashes['runner.py'],
            'frozen_capsule_manifest_sha256': capsule_hash,
            'frozen_capsule_path': str(snapshot), 'cancel_requested': False}},
    'invocation_notes': [
        'Parent independently reviews these exact source hashes and capsule, then registers the exact lease in the authoritative ledger. Preparation does not grant acceptance or launch authority.',
        'Run the capsule copy with python/.venv/bin/python. The legacy learning/.venv is never used. CLI requires --protocol and --output; --state-path defaults to the original production ledger.',
        'All capsule files and ancestor directories are mode 0444/0555. Runtime input verification includes original 75 pins and capsule copies, protocol, identity, three checkpoints, two controls, own helper source, interpreter and foundation binary/receipt pins. The mutable ledger and campaign logs are not hashed as inputs.',
        'The supervisor starts one new-session worker. The separate diagnostic guard checks the new lease and has no overnight cutoff or training-receipt dependency. Existing supervision.Guard/check_budget are unchanged.',
        'The 600 seconds begin at supervisor module startup and include imports, loads, evaluations, logging, controls, analysis, worker receipts and all normal finalization. The watchdog samples every 0.25 seconds, fails closed above a 0.5-second sample gap, and checks each inference/step boundary.',
        'Cleanup sends signals only to the owned new-session group and reaps its leader, with a separate bounded reserve. Final stable artifact hashing occurs after worker exit. No retry/fallback is available.',
        'Only exact complete failed-run diagnostic weights are read with weights_only=True and the prior narrow NumPy safe globals. No optimizer, RNG or episode restoration and no eligibility calls occur.',
        'Exact original entry and phase96 controls gate all sampled episodes. Phase104 is a new baseline. Exact sorted active B1 batching, direct D seeds, K4, caps and endpoint rows are preserved.',
        'Sample controller seeds are set once per checkpoint/replicate after loading. The seed-cluster bootstrap averages three replicates within each seed, uses 10000 shared-index resamples and the fixed 764002 seed.',
        'Decision traces retain all nine actual probabilities, actions, entropy and margins. Context counts and first observed pattern visibility are logged, with death cause UNKNOWN. No checkpoint selection or automatic learner action is produced.'
    ],
    'limitations': [
        'Native gameplay, full teacher loading/forward, MPS runtime behavior, historical control replay, throughput, 768-episode completion and real campaign resource use remain unverified by design. No real gameplay smoke was run.',
        'The tests validate fake CPU policies/environments and fixture supervisors. They do not establish that logging and inference will fit 600 seconds. A timeout must remain a retained failed diagnostic without retries.',
        'Memory guards are sampled RSS/MPS plus process self peak, not hard OS allocation limits. Missed sample cadence is a failure. A temporary identity change between samples cannot be ruled out by hash sampling.',
        'The pinned runtime identity covers the registered interpreter hash, Torch/NumPy versions, platform and native extension hash; it is not a byte inventory of every installed dependency/shared library.',
        'All r1 and r2 development failures, sources and receipts remain byte-identical. R3 preparation logs are retained. Final validation reruns all44original cases plus28finalization/cancellation cases on delivered hashes;12selected cases fail semantically against exactr1 and8cancellation cases fail semantically against exactr2.',
        'If worker termination/reaping cannot be established, the run remains failed and no stable artifact manifest is claimed. Partial decision/evaluation logs remain available; exact inference counts can be unknown if a worker was killed before its receipt.'
    ],
    'preparation_finished_at_utc': datetime.now(timezone.utc).isoformat(),
    'receipt_script_wall_seconds': time.monotonic() - started,
    'preparation_budget_about_seconds': 900,
    'checkpoint_input_snapshot_copies': 3,
    'checkpoint_files_written_count_scope': 'Zero learner checkpoint creation/reserialization. Three byte-identical read-only checkpoint input copies in candidate capsule.',
    'children_launched': 0, 'external_messages': 0,
    'automatic_campaign_retries': 0
}
assert not (ROOT / p['output']).exists()
write(HERE / 'implementation-result.json', result)
for name in ('implementation-result.json', 'test-receipt.json', 'source-manifest.json'):
    subprocess.run([str(ROOT / 'python/.venv/bin/python'), '-m', 'json.tool', str(HERE / name)],
                   stdout=subprocess.DEVNULL, check=True)
write(HERE / 'artifact-manifest.json', {str(x.relative_to(HERE)): sha(x)
      for x in sorted(HERE.rglob('*')) if x.is_file()})
print(json.dumps({'status': result['status'], 'tests': receipt['test_count'],
                  'runner_sha256': source_hashes['runner.py'],
                  'capsule_manifest_sha256': capsule_hash, 'capsule_files': len(files),
                  'campaign_launched': False}, sort_keys=True))
