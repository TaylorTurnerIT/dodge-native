"""Audit archived T4 evidence without executing a model or allocating a VM.

Original DODGE-060 remains failed. This audit records the already successful
GPU checks separately, preserving the missing inner field and using explicit
outer scope declarations plus exact producer source and artifact inventory.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'learning/runs/v2/teacher-cloud-parent-20261031-r1'
BASE = ROOT / 'learning/experiments/coordinator_dispatch_v2.py'
BASE_SHA = '77655f4e200ccce33950cd53201ef509394f8bff81e92fdd208c52668890fa16'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
if sha(BASE) != BASE_SHA: raise ValueError('Immutable ledger dependency changed')
spec = importlib.util.spec_from_file_location('archived_evidence_base', BASE)
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
need, read, save = base.need, base.read, base.save


def validate_receipts(path, nonce, payload_sha, reg=None):
    """Read JSON members without extracting links, paths, or tensor files."""
    needed = {'bootstrap-result.json', 'CUDA-compatibility.json', 'watchdog.json'}
    claims = {'CUDA-compatibility.json.claimed', 'watchdog.json.claimed'}
    logs = {'watchdog.json.stdout', 'watchdog.json.stderr'}
    docs, sidecars, seen = {}, {}, set()
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        need(len(members) <= 32 and sum(m.size for m in members) <= 4 * 1024 * 1024,
             'Receipt archive too large')
        for member in members:
            name = PurePosixPath(member.name)
            need(not name.is_absolute() and '..' not in name.parts and member.isfile()
                 and member.name not in seen, 'Unsafe receipt member')
            seen.add(member.name)
            need('failure' not in member.name, 'Failure receipt present')
            need(name.suffix == '.json' or member.name in claims | logs, 'Unexpected receipt sidecar')
            data = archive.extractfile(member).read()
            if member.name in logs:
                sidecars[member.name] = data
            else:
                docs[member.name] = json.loads(data)
    need(needed <= set(docs), 'Required receipt missing')
    need(not any('failure' in name for name in docs), 'Failure receipt present')
    schemas = {'bootstrap-result.json': 'dodge_colab_synthetic_receipt_bundle_v1',
               'CUDA-compatibility.json': 'dodge_colab_synthetic_compatibility_result_v1',
               'watchdog.json': 'dodge_colab_synthetic_watchdog_result_v1'}
    for name in needed:
        doc = docs[name]
        need(doc['schema'] == schemas[name] and doc['record'] == 'DODGE-060'
             and doc['job_nonce'] == nonce and doc['payload_sha256'] == payload_sha,
             'Receipt identity differs')
        need(doc['native_games'] == doc['training_frames'] == 0, 'Receipt exceeds synthetic scope')
        if name == 'CUDA-compatibility.json':
            # The exact archived producer omitted this field. Preserve that
            # absence; require two explicit companion declarations instead.
            need('trained_weights_saved' not in doc, 'Unexpected archived CUDA schema')
            need(docs['bootstrap-result.json']['trained_weights_saved'] is False
                 and docs['watchdog.json']['trained_weights_saved'] is False,
                 'Explicit companion no-trained-weights evidence absent')
        else:
            need(doc['trained_weights_saved'] is False, 'Receipt exceeds synthetic scope')
    need(docs['watchdog.json']['owned_group_absent'] is True, 'Remote group not absent')
    need(docs['bootstrap-result.json']['status'] == 'complete'
         and docs['watchdog.json']['status'] == 'complete'
         and docs['watchdog.json']['child_returncode'] == 0
         and docs['CUDA-compatibility.json']['status'] == 'synthetic_420_migration_passed',
         'Synthetic receipt reports failure')
    result, watchdog = docs['CUDA-compatibility.json'], docs['watchdog.json']
    need(result['device'] == watchdog['device'] == 'cuda' and result['device_index'] == 0
         and result['GPU'] in {'Tesla T4', 'NVIDIA T4'}
         and result['same_device_zero_gate_exact'] is True
         and result['synthetic_optimizer_steps'] == 1
         and result['CPU_device_numeric_tolerance'] == {'atol': 2e-5, 'rtol': 2e-5},
         'CUDA fixture/device contract differs')
    for key in ['peak_RSS_bytes', 'accelerator_peak_reserved_bytes', 'accelerator_peak_allocated_bytes']:
        need(type(result[key]) is int and 0 < result[key] < 6 * 2**30, 'CUDA fixture memory limit differs')
    for key in ['peak_group_RSS_bytes', 'peak_sampled_CUDA_driver_process_bytes']:
        need(type(watchdog[key]) is int and 0 < watchdog[key] < 6 * 2**30,
             'Watchdog memory limit differs')
    if reg is not None:
        need(claims | logs <= seen, 'Required emitted receipt sidecar missing')
        child_claim = docs['CUDA-compatibility.json.claimed']
        watch_claim = docs['watchdog.json.claimed']
        need(child_claim['device'] == 'cuda' and child_claim['job_nonce'] == nonce
             and watch_claim['record'] == 'DODGE-060' and watch_claim['job_nonce'] == nonce
             and watch_claim['payload_sha256'] == payload_sha
             and all(type(claim['pid']) is int and claim['pid'] > 0 for claim in [child_claim, watch_claim]),
             'Receipt claim identity differs')
        need(json.loads(sidecars['watchdog.json.stdout']) == result,
             'Child stdout/result receipt differs')
        cpu = read(reg['CPU_420_receipt_path'])
        need(result['platform'] == 'linux' and result['checkpoint_sha256'] ==
             '7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b'
             and result['source_model_fingerprint'] == cpu['source_model_fingerprint']
             and result['source_Adam_fingerprint'] == cpu['source_Adam_fingerprint']
             and result['migration'] == cpu['migration']
             and result['seed_pool_opened'] is result['heldout_opened'] is
                 result['simulator_restored'] is False,
             'Remote migration/scope receipt differs')
        expected_origins = cpu['runtime_origins']
        need(set(result['runtime_origins']) == set(expected_origins), 'Remote runtime origin set differs')
        for name, origin in result['runtime_origins'].items():
            relative = PurePosixPath(origin['path']).relative_to(PurePosixPath(reg['remote_root']) / 'source')
            local = str(Path(reg['source_root']) / str(relative))
            need(reg['source_pins'].get(local) == origin['sha256'] == expected_origins[name]['sha256'],
                 'Remote runtime source hash differs')
        provenance = docs['CUDA-compatibility.json.runtime-provenance.json']
        need(provenance['record'] == 'DODGE-060' and provenance['job_nonce'] == nonce
             and provenance['package_origins'] == result['package_origins'],
             'Remote pre-work provenance differs')
        need(set(result['package_origins']) == {'python', 'torch_python', 'torch_native',
             'numpy_python', 'numpy_native'}, 'Remote package provenance incomplete')
        for origin in result['package_origins'].values():
            need(PurePosixPath(origin['path']).is_absolute() and len(origin['sha256']) == 64
                 and all(x in '0123456789abcdef' for x in origin['sha256']),
                 'Remote package fingerprint malformed')
        for key in ['torch', 'numpy', 'python', 'cuda_runtime']:
            need(isinstance(result[key], str) and result[key] and provenance[key] == result[key],
                 'Remote version provenance differs')
    return docs


def load_reader(reg):
    path = Path(reg['original_controller_path'])
    need(sha(path) == reg['original_controller_sha256'], 'Original reader changed')
    spec = importlib.util.spec_from_file_location('preserved_original_T4_reader', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def validate_evidence(reg):
    need(reg['schema'] == 'dodge_colab_archived_evidence_registration_v1'
         and reg['record'] == 'DODGE-061' and reg['new_allocations_authorized'] == 0,
         'Audit-only scope differs')
    for path, digest in {**reg['source_pins'], **reg['input_pins']}.items():
        need(sha(path) == digest, 'Audit source/input changed')
    authority = read(reg['authority_path'])
    need(sha(reg['authority_path']) == reg['authority_sha256']
         and authority['record'] == 'DODGE-061'
         and authority['new_allocations_authorized'] == 0
         and authority['new_training_authorized'] is False
         and authority['previous_lease'] == reg['previous_lease']
         and authority['expected_lease'] == reg['expected_lease']
         and authority['state_path'] == reg['state_path'], 'Audit authority differs')
    original_path = Path(reg['original_registration_path'])
    need(sha(original_path) == reg['original_registration_sha256'], 'Original registration changed')
    original = read(original_path)
    need(reg['previous_lease'] == original['expected_lease']
         and reg['state_path'] == original['state_path']
         and reg['expected_lease']['record'] == 'DODGE-061'
         and reg['expected_lease']['promoted'] is False,
         'Audit/global ownership binding differs')
    for path, digest in {**original['source_pins'], **original['input_pins']}.items():
        need(sha(path) == digest, 'Original060 pin changed')
    out = Path(reg['original_output'])
    failure = read(out/'first-failure.json'); claim = read(out/'dispatch.claimed')
    need(failure['exception_type'] == 'KeyError' and failure['phase'] == 'retrieval'
         and claim['registration_sha256'] == reg['original_registration_sha256'],
         'Original reporting failure differs')
    need(not any((out/name).exists() for name in
         ['coordinator-terminal-audit.json','lease-release.json','parent-terminal-audit.json']),
         'Original060 unexpectedly accepted or released')
    reader = load_reader(reg)
    try:
        reader.validate_receipts(out/'receipts.tar', claim['notebook_hash'],
                                 original['payload_sha256'], original)
    except KeyError as error:
        need(error.args == ('trained_weights_saved',), 'Different original reader failure')
    else:
        raise ValueError('Original reader failure no longer reproducible')
    need(sha(out/'receipts.tar') == reg['archive_sha256'], 'Archived GPU result changed')
    with tarfile.open(out/'receipts.tar') as archive:
        names = [m.name for m in archive.getmembers()]
    need(set(names) == set(reg['exact_archive_members']) and len(names) == len(set(names)),
         'Archived artifact inventory differs')
    docs = validate_receipts(out/'receipts.tar', claim['notebook_hash'], original['payload_sha256'], original)
    result, watchdog = docs['CUDA-compatibility.json'], docs['watchdog.json']
    need(watchdog['error'] is None, 'Archived watchdog reports an error')
    need(watchdog['child_pid'] == docs['CUDA-compatibility.json.claimed']['pid'],
         'CUDA child identity differs')
    differences = result['CPU_device_max_absolute_differences']
    need(set(differences) == {'latent','logits','values'}
         and all(type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 2e-5
                 for v in differences.values()), 'Archived numeric difference exceeds bound')
    need(0 < result['elapsed_seconds'] <= 300 and 0 < watchdog['elapsed_seconds'] <= 315,
         'Archived work/receipt deadline differs')
    cleanup = read(out/'teardown.json')
    elapsed = cleanup['elapsed_assigned_seconds_upper_bound']
    combined = max(cleanup['cumulative_assigned_seconds_upper_bound'],
                   original['prior_assigned_seconds_upper_bound'] + elapsed)
    cost = max(cleanup['cumulative_cost_upper_estimate_CU'],
               original['prior_cost_upper_estimate_CU'] + cleanup['observed_debit_CU'] + elapsed*3/3600)
    need(cleanup['status'] == 'owned_assignment_absent'
         and cleanup['removal_classification'] == 'coordinator_requested_release'
         and cleanup['budget_within_limits'] is True
         and 0 < elapsed <= 860 and combined <= 900 and 0 <= cost <= 8,
         'Archived teardown/combined allowance differs')
    bills = [json.loads(row) for row in (out/'billing.jsonl').read_text().splitlines()]
    need(bills and all(b['fixtures_admitted'] is True and 0 < b['live_rate_CU_per_hour'] <= 3
                      for b in bills), 'Archived price admission differs')
    return dict(status='archived_T4_checks_verified_pending_independent_acceptance',
        record='DODGE-061', original_record='DODGE-060', original_campaign_success=False,
        archive_sha256=reg['archive_sha256'], original_missing_field_preserved=True,
        no_trained_weights_evidence={'bootstrap_explicit_false':True,'watchdog_explicit_false':True,
                                    'exact_source_and_artifact_inventory_verified':True},
        GPU=result['GPU'], device_index=result['device_index'], model_Adam_migration_passed=True,
        disposable_optimizer_steps=result['synthetic_optimizer_steps'],
        same_device_zero_gate_exact=result['same_device_zero_gate_exact'],
        CPU_CUDA_max_absolute_differences=differences,
        peak_RSS_bytes=result['peak_RSS_bytes'],
        peak_Torch_reserved_bytes=result['accelerator_peak_reserved_bytes'],
        peak_driver_process_bytes=watchdog['peak_sampled_CUDA_driver_process_bytes'],
        combined_assigned_seconds_upper_bound=combined, combined_cost_upper_estimate_CU=cost,
        native_games=0, training_frames=0, new_VM_allocations=0, A100_training_qualified=False)


def finalize(reg, review_path, review_sha, output, snapshot):
    output = Path(output)
    need(sha(review_path) == review_sha, 'Audit review hash differs')
    review = read(review_path)
    need(review['status'] == 'no_blocking_findings'
         and review['registration_sha256'] == reg['_registration_sha256']
         and review['audit_source_pins'] == reg['source_pins'],
         'Exact independent audit review absent')
    need(output.parent.resolve() == PARENT.resolve() and not output.is_symlink(),
         'Audit output namespace differs')
    need(not output.exists(), 'Audit finalization already consumed; never repeat')
    evidence = validate_evidence(reg)
    current = snapshot()
    need(current['raw']['assignmentsCount'] == 0 and not current['assignments'],
         'Fresh account absence not confirmed')
    output.mkdir()
    save(output/'audit.claimed', dict(record='DODGE-061',registration_sha256=reg['_registration_sha256'],
                                    review_sha256=review_sha,allocations=0))
    disposition_sha = save(output/'failed060-disposition.json', dict(status='acknowledged_failed_campaign',
        record='DODGE-060',campaign_success=False,original_registration_sha256=reg['original_registration_sha256'],
        exact_lease=reg['previous_lease'],reason='Preserved local report-contract failure; no old acceptance waiver.'))
    try:
        base.exact_handoff(reg['state_path'], reg['previous_lease'], reg['expected_lease'])
        save(output/'lease-handoff.json',dict(status='exact_non_null_failed_campaign_to_audit_handoff',
            previous_lease=reg['previous_lease'],replacement_lease=reg['expected_lease'],
            failure_disposition_sha256=disposition_sha,never_cleared_to_null=True))
        current = snapshot()
        need(current['raw']['assignmentsCount'] == 0 and not current['assignments'],
             'Fresh assignment absence lost before audit acceptance')
    except BaseException as error:
        save(output/'first-failure.json',dict(status='audit_failure_ownership_preserved',
            exception_type=type(error).__name__,no_allocations=True))
        raise
    audit = dict(evidence,status='accepted_archived_synthetic_T4_evidence',
        registration_sha256=reg['_registration_sha256'],review_sha256=review_sha,
        original060_preserved_as_failed=True,new_training_authorized=False,
        limits='Retrospective archive audit; original060 stays failed. No new GPU work, A100/native training, evaluation or promotion.')
    absence_sha = save(output/'account-absence.json',dict(record='DODGE-061',
        status='fresh_authenticated_zero_assignments',raw=current['raw'],assignments=[]))
    audit['account_absence_sha256'] = absence_sha
    import fcntl
    state_path=Path(reg['state_path'])
    with (state_path.parent/'horizon-ledger.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=read(state_path)
        need(state.get('active_long_campaign')==reg['expected_lease'],'Exact audit lease differs')
        audit_sha=save(output/'coordinator-terminal-audit.json',audit)
        state['active_long_campaign']=None
        temporary=state_path.parent/('.archive-audit-release-'+str(os.getpid()))
        with temporary.open('x') as f:
            json.dump(state,f,sort_keys=True,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(temporary,state_path);base.fsync_dir(state_path.parent)
    save(output/'lease-release.json',dict(status='coordinator_exact_release_completed',record='DODGE-061',
        accepted_audit_sha256=audit_sha,previous_lease=reg['expected_lease'],lease_value_after_release=None))
    return audit


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--registration',required=True);parser.add_argument('--sha256',required=True)
    parser.add_argument('--review');parser.add_argument('--review-sha256');parser.add_argument('--output')
    parser.add_argument('--finalize',action='store_true');args=parser.parse_args()
    need(sha(args.registration)==args.sha256,'Audit registration hash differs')
    reg=read(args.registration);reg['_registration_sha256']=args.sha256
    if not args.finalize:
        print(json.dumps(validate_evidence(reg),sort_keys=True));return
    original=read(reg['original_registration_path']);reader=load_reader(reg)
    planpath=Path(reg['original_plan_path'])
    transport=reader.SDKTransport(planpath,reg['original_plan_sha256'],original,reg['original_output'])
    result=finalize(reg,args.review,args.review_sha256,args.output,lambda:transport.snapshot(timeout=15))
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
