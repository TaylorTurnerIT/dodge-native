"""Prepare one fresh local066 packet from immutable056 source and runtime."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
OLD = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-teacher-ray-geometry-20261030/learning/runs/v2/teacher-ray-screen-20261030-r4')
PACKET = ROOT/'learning/runs/v2/teacher-ray-local-20261031-r1'
PARENT = ROOT/'learning/runs/v2/teacher-local-parent-20261031-r1'
SOURCE = ROOT/'learning/experiments/teacher_local_dispatch_20261031_r1.py'
spec = importlib.util.spec_from_file_location('local066_prepare_parent', SOURCE)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


def main():
    oldpath = OLD/'registration-r4.json'
    c.need(c.sha(oldpath) == '1881aad8554a0841246248c2cb0e6ae49dc425716f924b6824b440eeaa53a94e', 'Original056 identity differs')
    old = c.read(oldpath)
    for path, digest in {**old['source_pins'], **old['input_pins']}.items():
        c.need(c.sha(path) == digest, 'Original056 frozen pin changed')
    c.need(not PACKET.exists() and not PARENT.exists(), 'Fresh local source/parent required')
    disposition = c.failed_disposition()
    c.need(c.read(old['state_path'])['active_long_campaign'] == disposition['exact_lease'], 'Failed065 lease differs')
    PACKET.mkdir(); PARENT.mkdir()
    for name in ['common.py','worker.py','run_once.py','lifecycle.py','fingerprints.py','update_telemetry.py',
                 'cpu_preflight.py','test_source.py','evaluate_worker.py','evaluation_analysis.py']:
        shutil.copyfile(OLD/name, PACKET/name)
    shutil.copytree(OLD/'runtime', PACKET/'runtime')
    p = PACKET/'common.py'; p.write_text(p.read_text().replace("reg['record'] == 'DODGE-056'", "reg['record'] == 'DODGE-066'"))
    p = PACKET/'run_once.py'; text = p.read_text().replace('DODGE-056', 'DODGE-066').replace('DODGE-055', 'DODGE-065')
    text = text.replace("'teacher_training_queue_authority_v3'", "'teacher_local_authority_v1'")
    p.write_text(text)
    p = PACKET/'test_source.py'; text = p.read_text().replace('DODGE-056', 'DODGE-066').replace('DODGE-055', 'DODGE-065')
    p.write_text(text)
    reg = copy.deepcopy(old)
    authority_path = PARENT/'authority-local066-r1.json'
    authority = dict(schema='teacher_local_authority_v1', execution_location='local_machine_only',
        user_quotes=["We're done with trying to use collab. Go back to using exclusively on machine.",
                     "I'm tired of waiting. Let's get actual training going again."],
        predecessor_record='DODGE-065', successor_record='DODGE-066', fresh_successor_attempts_authorized=1,
        first_screens_only=True, no_claim_or_lease_reset=True, evaluation_authorized=False, promotion=False,
        limits=dict(AC_required=False, battery_operation_allowed=True, work_seconds=7200,
            receipt_seconds=180, campaign_total_seconds=29520, rss_bytes=6*2**30, mps_bytes=6*2**30),
        timing_reason='New successor budget reflects observed056125.8739second prefix update; old5400second cap and failed status remain immutable. Same frames, optimizer and streams; no new learning rule or automatic stopping gate.')
    c.save(authority_path, authority)
    expected = dict(kind='teacher_ray_training_screen', record='DODGE-066', run_id=PACKET.name,
        package=str(PACKET), owner_token='rays066-local-20261031-r1', promoted=False)
    reg.update(record='DODGE-066', package=str(PACKET), run_id=PACKET.name, revision=1,
        runtime_root=str(PACKET/'runtime'), expected_lease=expected, authority_path=str(authority_path),
        authority_sha256=c.sha(authority_path), work_seconds=7200, campaign_total_seconds=29520,
        failed_predecessor=dict(record='DODGE-065', registration_path=str(c.FAILED/'DODGE-065-A100-bootstrap-registration-r1.json'),
            registration_sha256=c.FAILED_REG_SHA, expected_lease=disposition['exact_lease'], campaign_success=False),
        launch_authority=False, evaluation_games=0, execution_location='local_machine_only',
        queue_role='Historical only. Fresh local authority supersedes cloud execution; no Colab use.',
        local_timing_change=authority['timing_reason'])
    reg.pop('evaluation', None); reg.pop('evaluation_expected_lease', None)
    reg['declared_failed_histories'].update({x:'failed immutable; no retry or success waiver' for x in ['DODGE-056','DODGE-058','DODGE-062','DODGE-064','DODGE-065']})
    reg['coordinator_source_pins'] = {str(SOURCE):c.sha(SOURCE), str(c.BASE):c.BASE_SHA}
    reg['source_pins'] = {str(p):c.sha(p) for p in PACKET.glob('*.py')}
    reg['source_pins'].update(reg['coordinator_source_pins']); reg['source_pins'][str(Path(__file__).resolve())] = c.sha(__file__)
    reg['input_pins'] = dict(old['input_pins'])
    reg['input_pins'].update({str(p):c.sha(p) for p in (PACKET/'runtime').rglob('*') if p.is_file()})
    reg['input_pins'].update({str(authority_path):c.sha(authority_path), str(oldpath):c.sha(oldpath)})
    predictions = PACKET/'predictions.json'
    c.save(predictions, dict(record='DODGE-066', timing='before_execution',
        doing='Original420+Adam entity control versus static R0 rays on local MPS; two paired replicas in ABBA order.',
        expected='Learning and survival improvement remain unknown. Same36updates and2359296actualK1frames/job; local timing budget may accommodate previously observed runtime.',
        why='Return to on-machine execution after abandoning Colab; preserve056scientific recipe and all failed histories.', actual=None))
    reg['input_pins'][str(predictions)] = c.sha(predictions)
    for key in ['arms','ppo','replicas','jobs','checkpoint_path','checkpoint_sha256','model_fingerprint','adam_fingerprint',
                'exclusions','frame_target','updates','envs','rollout','microbatch','effective_minibatch','runtime_members']:
        c.need(reg[key] == old[key], 'Original science differs: '+key)
    for member in reg['runtime_members']:
        c.need(c.sha(PACKET/'runtime'/member) == old['input_pins'][str(OLD/'runtime'/member)], 'Runtime copy differs')
    c.save(PACKET/'registration-r1.json', reg)
    (PACKET/'empty-pycache').mkdir(); (PACKET/'outputs').mkdir()
    for job in reg['jobs']: (PACKET/'outputs'/job['id']).mkdir()
    c.save(PARENT/'failed065-disposition-preparation.json', disposition)
    print(json.dumps(dict(registration_path=str(PACKET/'registration-r1.json'),
        registration_sha256=c.sha(PACKET/'registration-r1.json'), launch_claimed=False, lease_mutated=False)))


if __name__ == '__main__': main()
