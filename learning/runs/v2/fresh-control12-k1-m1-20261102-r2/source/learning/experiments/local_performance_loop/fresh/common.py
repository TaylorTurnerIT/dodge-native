"""Fresh-stream profile; reuse M1 admission and accepted lifecycle helpers."""
import importlib.util
from pathlib import Path
import sys

CODE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_fresh_reused_common', CODE.parent/'continuation/common.py')
accepted = importlib.util.module_from_spec(spec); spec.loader.exec_module(accepted)
for name in dir(accepted):
    if not name.startswith('_') and name not in ('CODE', 'HERE', 'RUN'):
        globals()[name] = getattr(accepted, name)
HERE = CODE
RUN = None
sys.path.insert(1, str(CODE.parent/'continuation'))
from seed_bank import specification, audit_assignments


def validate_shape(reg, recipe):
    need(reg['schema'] == 'local_performance_fresh_v1' and reg['job_order'] == ['control'], 'Fresh control scope differs')
    need(not reg['cloud_authorized'] and not reg['promotion'] and reg['no_retry'] and reg['no_automatic_resume'],
         'First-attempt/local-only controls differ')
    need((reg['envs'], reg['rollout'], reg['action_repeat'], reg['effective_minibatch'], reg['microbatch'])
         == (64, 1024, 1, 2048, 512), 'Accepted K1 shape differs')
    need(reg['ppo'] == recipe['ppo'] and reg['ppo']['learning_rate'] == 3e-5
         and reg['arms'] == {'control': recipe['arms']['control']}, 'Fresh seeds are the only recipe change')
    need((reg['initial_updates'],reg['segment_updates'],reg['prefix_updates']) == (72,12,2), 'Play cadence differs')
    need(reg['work_seconds'] is None and reg['total_seconds'] is None and not reg['forecast_fit_gate'],
         'No wall-clock cancellation or forecast admission')
    need(reg['rss_bytes'] == reg['mps_bytes'] == 6*1024**3, 'Separate memory ceilings differ')
    need(reg['warmstart']['sha256'] == '04171886ad1d200f58579952519e972610f9518ddd32af54d25b817204d072b8'
         and reg['checkpoint_sha256'] == '7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b',
         'Preserved control12 and420 required; no071 endpoint')
    need(reg['exclusions'] == recipe['exclusions'], 'Reserved exclusion ranges differ')
    need(reg['evaluation_seeds'] == list(range(3657433088,3657433600))
         and reg['evaluation_controller_domain'] == 'dodge068/paired-policy-v1', 'Consumed development semantics differ')
    need(reg['fresh_stream']['bank_episodes_per_slot'] == 72*1024+1, 'Bounded stream bank differs')
    need(reg['policy']['initial_updates'] == 72 and reg['policy']['segment_updates'] == 12
         and reg['policy']['minimum_Q1_fraction'] == .9 and reg['policy']['early_death_allowance_fraction'] == .02
         and reg['policy']['gain_fraction'] == .02 and reg['policy']['patience_checks'] == 3, 'Mean play policy differs')
    need(reg['policy']['max_checks'] == 2438 and reg['max_updates'] == 2438*12
         and reg['frame_target'] == reg['max_updates']*65536, 'Finite progress bound differs')
    need(set(reg['baseline_sources']) == {'420','control12'}
         and reg['baseline_source_registration_sha256'] == '2f9adc5af999020da9278d094cc5fc4abece2fae87642197d8d114e0618f5b5d',
         'Exact accepted same-M1 baselines required')


def validate_baseline_binding(reg, prior):
    need(prior['machine'] == reg['machine'] and prior['runtime_root'] == reg['runtime_root']
         and prior['runtime_members'] == reg['runtime_members']
         and prior['evaluation_seeds'] == reg['evaluation_seeds']
         and prior['evaluation_controller_domain'] == reg['evaluation_controller_domain']
         and prior['exclusions'] == reg['exclusions']
         and prior['warmstart']['sha256'] == reg['warmstart']['sha256']
         and prior['checkpoint_sha256'] == reg['checkpoint_sha256'], 'Cached baseline provenance incompatible')
    for member in reg['runtime_members']:
        path=str(Path(reg['runtime_root'])/member)
        need(prior['input_pins'][path] == reg['input_pins'][path], 'Cached baseline runtime source differs')


def load_registration(path, digest):
    global RUN
    need(sha(path) == digest, 'Fresh registration hash differs')
    reg=read(path)
    # This gate precedes any output, process, model/native import or lease.
    need(reg['execution_authorized'] and reg['training_authorized'] and reg['fresh_games_authorized'],
         'Source-only candidate: separate fresh-games execution disposition required')
    authority=read(reg['authority_path'])
    need(authority['training_execution_authorized'] and authority['fresh_games_authorized']
         and authority['record'] == reg['record'] and authority['run_id'] == reg['run_id']
         and authority['one_invocation'] and authority['prepared_candidate_sha256'] == reg['prepared_candidate_sha256']
         and authority['checkpoint_sha256'] == reg['warmstart']['sha256']
         and authority['original_adam_fingerprint'] == reg['warmstart']['adam_fingerprint']
         and authority['source_LR_unchanged'] == reg['ppo']['learning_rate']
         and authority['seed_stream_identity'] == reg['fresh_stream']['stream_identity'],
         'Current source-preparation instruction is not execution authority')
    RUN=Path(reg['run_dir']).resolve(); accepted.RUN=RUN; accepted.base.RUN=RUN
    need(Path(reg['runner']).resolve() == CODE and reg['expected_lease']['package'] == str(RUN)
         and reg['expected_lease']['owner_token'] == reg['run_id'] and reg['expected_lease']['machine'] == reg['machine'],
         'Machine-bound successor package/lease identity differs')
    validate_shape(reg, read(reg['source_config_path']))
    verify_pins(reg); verify_runtime_members(reg)
    need(not list(Path(reg['cache']).rglob('*')), 'Bytecode cache changed')
    need(read(reg['accepted067_path'])['status'] == 'accepted_local_performance_loop'
         and read(reg['accepted_M1_path'])['status'] == 'accepted_M1_import_tiny_device_only', 'Accepted input proof missing')
    need(read(reg['closed071_audit'])['status'] == 'accepted_local_control_continuation'
         and read(reg['closed071_release'])['accepted_audit_sha256'] == sha(reg['closed071_audit'])
         and read(reg['closed071_release'])['lease_value_after_release'] is None, '071 closeout proof differs')
    prior=read(reg['baseline_source_config'])
    need(sha(reg['baseline_source_config']) == reg['baseline_source_registration_sha256'], 'Cached source config hash differs')
    validate_baseline_binding(reg, prior)
    provenance=read(reg['development_provenance'])
    need(provenance['role'] == 'exposed_development_diagnostic_not_confirmation'
         and provenance['range_inclusive'] == [3657433088,3657435135], 'Development reuse provenance differs')
    specification(reg)  # Exclusion/key validation only; no seed lookup.
    return reg
