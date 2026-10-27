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
PROTOCOL = ROOT / 'learning/runs/v2-orchestration/postovernight-action-mode-r1-protocol.json'

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
for name in ('runner.py', 'test_harness.py', 'prepare_receipts.py'):
    files[str((HERE / name).relative_to(ROOT))] = sha(HERE / name)
for name, digest in files.items():
    assert sha(ROOT / name) == digest, name
initial.update({str(ROOT / name): digest for name, digest in files.items()})
foundation = json.loads((ROOT / p['foundation_identity_path']).read_text())
for name, digest in foundation['foundation']['binary_and_receipt_sha256'].items():
    assert sha(name) == digest, name
    initial[name] = digest

command = [str(ROOT / 'python/.venv/bin/python'), '-B', str(HERE / 'test_harness.py')]
source_hashes = {name: sha(HERE / name) for name in ('runner.py', 'test_harness.py', 'prepare_receipts.py')}
test_start = time.monotonic()
with (HERE / 'tests-final.log').open('x') as stream:
    completed = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=60)
test_wall = time.monotonic() - test_start
log = (HERE / 'tests-final.log').read_text()
match = re.search(r'Ran (\d+) tests in ([0-9.]+)s', log)
receipt = {'command': command, 'cwd': str(ROOT), 'exit_code': completed.returncode,
           'execution_source_sha256': source_hashes,
           'test_count': int(match[1]) if match else None,
           'reported_seconds': float(match[2]) if match else None,
           'wall_seconds': test_wall, 'log_sha256': sha(HERE / 'tests-final.log'),
           'scope': 'Standalone synthetic/pure CPU tests, fake tiny policies/environments, mocked probes, fixture leases, real bounded dummy subprocesses. Dodge imports are forbidden by an import guard. No actual teacher/native/model/MPS inference, no production campaign, no training.',
           'historical_test_counts_used': False}
write(HERE / 'test-receipt.json', receipt)
assert completed.returncode == 0 and receipt['test_count'] == 44, 'Final synthetic validation failed'
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
    'test_scope': receipt['scope'], 'test_command': command,
    'test_source_hashes': source_hashes,
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
        'The 600 seconds begin at supervisor module startup and include imports, loads, evaluations, logging, controls, analysis and worker receipts. The watchdog samples every 0.25 seconds, fails closed above a 0.5-second sample gap, and checks each inference/step boundary.',
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
        'Earlier development test logs retain two 36-test cleanup failures and later passing rounds. Only the final 44-test receipt is validation of the delivered execution source hashes. The first cleanup failure exposed a process-group disappearance/readiness race; readiness-aware dummy tests and retained probe failures now cover it.',
        'If worker termination/reaping cannot be established, the run remains failed and no stable artifact manifest is claimed. Partial decision/evaluation logs remain available; exact inference counts can be unknown if a worker was killed before its receipt.'
    ],
    'preparation_finished_at_utc': datetime.now(timezone.utc).isoformat(),
    'receipt_script_wall_seconds': time.monotonic() - started,
    'preparation_budget_about_seconds': 900,
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
