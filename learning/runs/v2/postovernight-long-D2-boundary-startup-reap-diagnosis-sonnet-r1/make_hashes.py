"""Hash-only helper. Reads inputs, writes input-hashes.json and output-receipt.json (receipt excludes itself)."""
import hashlib, json, sys
from pathlib import Path
root = Path('.')
out = Path(sys.argv[1])
r6 = Path('learning/runs/v2/postovernight-long-D2-boundary-prepare-r6')
case = r6 / 'attempts/attempt-03-focused-OS/cases/direct-cancel-startup'
def h(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
inputs = {}
for p in ['docs/implementation-plan-v2.md', 'docs/SPEC_PRIVILEGED_VIT_RL.md',
          'learning/runs/v2-orchestration/state.json',
          'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r5.json',
          'learning/runs/v2/postovernight-long-D2-boundary-failure-diagnosis-sonnet-r1/diagnosis.md',
          'learning/runs/v2/postovernight-long-D2-boundary-failure-diagnosis-sonnet-r1/output-receipt.json']:
    inputs[p] = h(p)
for name in ['parent-frozen-pins.json', 'protocol-r5-proposal.json', 'long_d2.py', 'long_d2_executor.py', 'lifecycle.py',
             'processes.py', 'synthetic.py', 'fixture_guards.py', 'os_checks.py', 'test_repairs.py', 'boundary_integrity.py',
             'registration.json']:
    inputs[str(r6 / name)] = h(r6 / name)
for p in sorted(case.rglob('*')):
    if p.is_file(): inputs[str(p)] = h(p)
inputs['mutable_context_note'] = 'state.json is mutable; hash is as read at proposal time'
(out / 'input-hashes.json').write_text(json.dumps(inputs, indent=2, sort_keys=True) + '\n')
files = {}
for p in sorted(out.iterdir()):
    if p.name == 'output-receipt.json' or not p.is_file(): continue
    files[p.name] = h(p)
receipt = dict(schema='boundary_startup_reap_diagnosis_output_receipt_v1', files=files,
               receipt_excludes_own_hash=True, source_written=False, capsule_written=False,
               state_protocol_docs_written=False, OS_cases_rerun=0, subprocesses_run=0, ML_native_imports=False,
               in_process_stdlib_probes=['dgram_close_probe.py'], hashing_helper='make_hashes.py',
               model='claude-sonnet-5-5')
(out / 'output-receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
