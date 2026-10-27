"""Static hash/AST/JSON review only. Never imports or executes target code."""
import ast
import hashlib
import json
from pathlib import Path

OWN = Path(__file__).resolve().parent
V2 = OWN.parent
TARGET = V2 / 'progressive1000-ps-timeout-repair-sol-20261027-r6'
BASE = V2 / 'progressive1000-supervisor-nonreaping-parent-completion-20261026-r5'
PROPOSAL = V2 / 'progressive1000-control-retry-proposal-parent-20261027-r1'
EXPECTED = '5d5ed45a982cde59f18a16f92cab4b7fd55a906640d5428eef63a07607bc9053'


def read(path):
    def unique(items):
        result = {}
        for key, value in items:
            assert key not in result, (path, key)
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (OWN / name).open('x') as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + '\n')


def metadata(path):
    if not path.exists():
        return None
    value = path.lstat()
    return dict(mode=value.st_mode, size=value.st_size, mtime_ns=value.st_mtime_ns,
                ctime_ns=value.st_ctime_ns, inode=value.st_ino)


def verify_manifest(home, filename='source-manifest.json'):
    manifest = read(home / filename)
    for name, digest in manifest['files'].items():
        path = home / name
        assert path.resolve().is_relative_to(home) and not path.is_symlink(), path
        assert sha(path) == digest, path
    return manifest


assert sha(TARGET / 'source-manifest.json') == EXPECTED
manifest = verify_manifest(TARGET)
baseline = verify_manifest(BASE)
pins = read(TARGET / 'source-pins.json')
immutable = pins['immutable_metadata_and_source_pins']
assert all(sha(Path(path)) == digest for path, digest in immutable.items())
protected = {Path(path) for path in immutable}
proposal = read(PROPOSAL / 'proposal.json')
candidate_path = PROPOSAL / 'registration-final-candidate.json'
original_path = Path(proposal['original_registration'])
candidate, original = read(candidate_path), read(original_path)
assert sha(original_path) == proposal['original_registration_sha256']
assert sha(candidate_path) == proposal['candidate_registration_sha256']
assert proposal['supervisor_source_manifest_sha256'] == EXPECTED
assert proposal['status'] == 'REQUIRES_EXPLICIT_USER_AUTHORIZATION_NO_LAUNCH'
assert proposal['attempt_number'] == 2 and proposal['original_attempt_remains_closed'] is True
assert all(proposal[key] is False for key in ('launch_approval_created', 'lease_installed',
                                            'marker_claimed', 'campaign_limits_increased',
                                            'training_seeds_replaced'))
protected.update([PROPOSAL / 'proposal.json', candidate_path, Path(original['state_path'])])
protected.update(TARGET / name for name in manifest['files'])
protected.update([TARGET / 'source-manifest.json', BASE / 'source-manifest.json'])
before = {str(path): metadata(path) for path in protected}
before_hashes = {str(path): sha(path) for path in protected if path != Path(original['state_path'])}

parsed = []
for name in manifest['files']:
    if name.endswith('.py'):
        ast.parse((TARGET / name).read_text(), filename=name)
        parsed.append(name)
unchanged = ['binding.py', 'terminal.py', 'execute_once.py', 'dependency-binding.json']
assert all((TARGET / name).read_bytes() == (BASE / name).read_bytes() for name in unchanged)
old = (BASE / 'observe.py').read_text()
expected = old.replace('def process_rows():\n',
    'def process_rows():\n    # The active supervisor SIGALRM enforces the original work/total budget.\n')
expected = expected.replace('capture_output=True, text=True, check=True, timeout=1)',
                            'capture_output=True, text=True, check=True)')
assert (TARGET / 'observe.py').read_text() == expected


def bodies(path):
    text = path.read_text()
    return {node.name: ast.get_source_segment(text, node) for node in ast.walk(ast.parse(text))
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')}


for name, count in [('test_bindings.py', 11), ('test_real_processes.py', 14)]:
    prior, current = bodies(BASE / 'tests' / name), bodies(TARGET / 'tests' / name)
    assert len(prior) == count and prior == current
assert len(bodies(TARGET / 'tests/test_ps_deadlines.py')) == 4
accepted = V2 / 'progressive1000-shared-runtime-staticmethod-repair-sol-20261026-r2'
accepted_source = verify_manifest(accepted)
runtime_manifest = read(accepted / 'runtime-manifest.json')
for name, digest in runtime_manifest['files'].items():
    assert sha(accepted / 'runtime' / name) == digest
assert sha(accepted / 'source-manifest.json') == candidate['source_manifest_sha256']
assert sha(accepted / 'runtime-manifest.json') == candidate['runtime_manifest_sha256']

differences = sorted(key for key in set(original) | set(candidate) if original.get(key) != candidate.get(key))
assert differences == ['attempt_claim_path', 'expected_lease', 'import_policy', 'launch_marker_path', 'output']
lease_differences = sorted(key for key in original['expected_lease']
                          if original['expected_lease'][key] != candidate['expected_lease'][key])
assert lease_differences == ['owner_token', 'registration_path']
assert candidate['expected_lease']['registration_path'] == str(candidate_path)
assert original['import_policy']['dont_write_bytecode'] is candidate['import_policy']['dont_write_bytecode'] is True
assert all(original[key] == candidate[key] for key in proposal['unchanged_learning_fields'])
fresh_paths = [Path(candidate[key]) for key in ('output', 'attempt_claim_path', 'launch_marker_path')]
fresh_paths.append(Path(candidate['import_policy']['pycache_prefix']))
assert len(set(fresh_paths)) == 4
assert all(path.resolve().parent == PROPOSAL and not path.is_symlink() for path in fresh_paths)
assert all(not path.exists() for path in fresh_paths[:3])
assert fresh_paths[3].is_dir() and not any(fresh_paths[3].iterdir())
assert set(path.name for path in PROPOSAL.iterdir()) == {'proposal.json', 'registration-final-candidate.json', 'empty-pycache'}
assert Path(original['launch_marker_path']).exists() and Path(original['attempt_claim_path']).exists()
for key in ('launch_marker_path', 'attempt_claim_path', 'output'):
    protected.add(Path(original[key]))
    before[str(Path(original[key]))] = metadata(Path(original[key]))

index = read(TARGET / 'template-index.json')
assert index['launch_authority'] is False and index['approval_templates_created'] == 0
registrations = pins['registrations']
assert len(registrations) == len(index['envelopes']) == 6
tokens = []
for item in registrations:
    path = Path(item['registration'])
    assert sha(path) == item['sha256']
    reg = read(path)
    tokens.append(reg['expected_lease']['owner_token'])
    if path != original_path:
        assert all(not Path(reg[key]).exists() for key in ('output', 'attempt_claim_path', 'launch_marker_path'))
assert candidate['expected_lease']['owner_token'] not in tokens
for item in index['envelopes']:
    path = TARGET / item['path']
    assert sha(path) == item['sha256']
    envelope = read(path)
    assert envelope['started'] is None and envelope['launch_approval_sha256'] is None
    assert all(sha(Path(path)) == digest for path, digest in envelope['pins'].items())
    if item['spent']:
        assert envelope['status'] == 'SPENT_CLOSED_NO_RETRY_NO_LAUNCH'
        assert envelope['registration'] == str(original_path)
        assert Path(envelope['control']).is_relative_to(BASE / 'dispatch')
    else:
        assert envelope['status'] == 'DRAFT_NO_LAUNCH'
assert not (TARGET / 'dispatch').exists()

suites = {}
for name, relative, count in [('fake', 'validation/fake/test-receipt.json', 11),
                              ('original_real', 'validation/real/real-test-receipt.json', 14),
                              ('ps_boundary', 'validation/ps/ps-test-receipt.json', 4)]:
    receipt = read(TARGET / relative)
    assert receipt['tests_run'] == count and receipt['successful'] is True
    assert receipt['failures'] == receipt['errors'] == receipt['raw_exit'] == 0
    assert receipt['forbidden_runtime_imports'] == []
    assert receipt.get('remaining_owned_handles', []) == []
    suites[name] = dict(path=relative, sha256=sha(TARGET / relative), tests=count,
                        reported_success=True, reviewer_replayed=False)
ps = read(TARGET / 'validation/ps/ps-test-receipt.json')
boundary = []
for case in ps['evidence']:
    checks, observation = case['checks'], case['observation']
    assert checks['worker_ECHILD_and_group_absent_before_teardown'] is True
    assert all(helper['ECHILD_confirmed'] and helper['group_absent']
               and helper['directly_reaped_before_test_teardown'] for helper in checks['ps_helpers'])
    boundary.append(dict(test=case['test'], checks=checks,
                         first_event=observation['first_event'],
                         deadline_consumed=observation['deadline_consumed'],
                         cleanup=observation['cleanup']))

audit_path = original_path.parent / 'parent-terminal-audit.json'
audit = read(audit_path)
compact_path = original_path.parent / 'compact-campaign-receipt.json'
compact = read(compact_path)
fields = ['run_id', 'completed_updates', 'first_failure', 'raw_observer_exit_code',
          'raw_worker_exit_code', 'directly_reaped', 'independent_process_groups',
          'immutable_inputs_dependencies_and_cache_postflight_pass', 'partial_checkpoints',
          'resource_samples', 'marker_and_transition_claim_preserved', 'comparison_endpoint_complete']
failure = {key: audit[key] for key in fields}
assert all(compact['terminal_audit'][key] == value for key, value in failure.items())
assert failure['completed_updates'] == 41 and failure['raw_worker_exit_code'] == -15
assert failure['directly_reaped'] and all(group['absent'] for group in failure['independent_process_groups'])
assert failure['immutable_inputs_dependencies_and_cache_postflight_pass'] is True
assert failure['comparison_endpoint_complete'] is False
assert [checkpoint['global_update'] for checkpoint in failure['partial_checkpoints']] == [12, 24, 36]
save('actual-failure-selection.json', dict(parent_audit_sha256=sha(audit_path),
    compact_receipt_sha256=sha(compact_path), selected_failure_identity_resource_metadata=failure,
    checkpoint_payloads_read=False, training_outcome_fields_inspected=False))
save('static-checks.json', dict(source_manifest_sha256=EXPECTED, source_files=len(manifest['files']),
    ast_parsed=parsed, unchanged_operational_files=unchanged,
    exact_observer_delta='Remove timeout=1; add budget-owner comment only.',
    accepted_source_files_hashed=len(accepted_source['files']),
    accepted_runtime_files_opaque_hashed=len(runtime_manifest['files']),
    named_immutable_pins_checked=len(immutable), original_controls_unchanged=25,
    additional_boundary_controls=4, inherited_suite_receipts=suites, ps_boundary_metadata=boundary))
save('candidate-compatibility.json', dict(original_registration_sha256=sha(original_path),
    candidate_registration_sha256=sha(candidate_path), changed_fields=differences,
    changed_lease_fields=lease_differences, exact_unchanged_fields=proposal['unchanged_learning_fields'],
    new_paths=[str(path) for path in fresh_paths], new_spend_paths_absent=True, new_cache_exists_empty=True,
    candidate_owner_token_unique_among_six_originals=True, original_marker_and_claim_present=True,
    original_five_other_registrations_unlaunched=True, spent_r6_envelope_closed=True,
    candidate_not_bound_to_executable_envelope=True, launch_approval_present=False,
    source_compatibility='compatible in principle; no preflight executed',
    authorization='absent; future explicit user authorization required before fresh approval, lease, marker or launch'))
after = {str(path): metadata(path) for path in protected}
assert before == after
assert all(sha(Path(path)) == digest for path, digest in before_hashes.items())
save('preservation.json', dict(metadata_before=before, metadata_after=after,
    named_bytes_before_and_after=before_hashes, metadata_drift=[], named_byte_drift=[],
    state_payload_read=False, checkpoint_payload_read=False,
    scope='Named source/registration/proposal bytes and named metadata during this static review only.'))
print(json.dumps(dict(status='static checks passed', source_manifest_sha256=EXPECTED,
    findings=0, reviewer_test_executions=0, prospective_retry_authorized=False)))
