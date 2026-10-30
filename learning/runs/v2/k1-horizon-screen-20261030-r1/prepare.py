"""Prepare a versioned registration; no Torch, games, claim, lease or seed reservation."""
import argparse
import datetime
import sys

import common as c


def registration(revision):
    root = c.HERE.parents[3]
    prior = root / 'learning/runs/v2/track-a-s1-successor-parent-20261030-r2/S1-registration.json'
    old = c.read(prior)
    formal_path = root / 'learning/runs/v2/one-frame-training-comparison-luna-20261029-r2/registration-formal-final-r5.json'
    formal = c.read(formal_path)
    inputs = {p: h for p, h in old['input_pins'].items()
              if '/runtime-clean-r2/' in p or p in [old['pool_path'], old['checkpoint_path'], old['interpreter']]}
    inputs[str(prior)] = c.sha(prior)
    inputs[str(formal_path)] = c.sha(formal_path)
    replicas = {}
    for replica in [1,2]:
        replicas[str(replica)] = dict(constructor_seed=202610301100 + replica,
            python_seed=202610301200 + replica, numpy_seed=(202610301300 + replica) % 2**32,
            torch_cpu_seed=202610301400 + replica, torch_mps_seed=202610301500 + replica,
            environment_seed=202610301600 + replica)
    reg = dict(schema='dodge_K1_horizon_training_registration_v1',
        run_id='K1-horizon-screen-20261030-r1', revision=revision, package=str(c.HERE),
        record='DODGE-050', proposal_path=str(root / 'learning/runs/v2/first-training-screen-parent-20261030-r1/first-horizon-screen-proposal.json'),
        interpreter=old['interpreter'], runtime_root=old['runtime_root'], pool_path=old['pool_path'],
        checkpoint_path=old['checkpoint_path'], checkpoint_sha256=old['checkpoint_sha256'],
        model_fingerprint=formal['model_fingerprint'], adam_fingerprint=formal['adam_fingerprint'],
        state_path=old['state_path'], source_pins={}, input_pins=inputs,
        expected_lease=dict(kind='K1_horizon_training_screen', run_id='K1-horizon-screen-20261030-r1',
            package=str(c.HERE), owner_token='horizon050-20261030-single-claim-r1', promoted=False),
        arms=dict(matched=dict(gamma=.995**.25, gae_lambda=.95**.25),
                  shorter=dict(gamma=.99, gae_lambda=.90)),
        jobs=[dict(id='r1-matched', replica='1', arm='matched'),
              dict(id='r1-shorter', replica='1', arm='shorter'),
              dict(id='r2-shorter', replica='2', arm='shorter'),
              dict(id='r2-matched', replica='2', arm='matched')], replicas=replicas,
        exclusions=old['excluded_seed_ranges'] + [[3657433088,3657435135]],
        envs=64, rollout=1024, frame_target=2359296, updates=36, microbatch=512,
        effective_minibatch=2048, threads=4, prefix_updates=2, checkpoint_updates=[12,24,36],
        ppo=dict(learning_rate=3e-5, adam_eps=1e-5, clip_coef=.2, vf_coef=.5, ent_coef=.01,
                 max_grad_norm=.5, update_epochs=4, minibatch_size=512, target_kl=.03, reward_scale=.1),
        work_seconds=5400, receipt_seconds=180, campaign_total_seconds=22320, IO_reserve_seconds=240,
        rss_bytes=6*2**30, mps_bytes=6*2**30, allocator_bytes=int(5.5*2**30),
        AC_required=True, one_MPS_job=True, no_retry=True, no_automatic_resume=True,
        promotion=False, launch_authority=False, evaluation_games=0,
        qualification='First2 counted updates of every trajectory: tensor/return identity, hooks, full update resource/timing and20% forecast. No discarded/repeated qualification training.',
        evaluation='Later separately reviewed evaluation packet; no new cohort reserved or opened by this training registration.',
        checkpoint_limit='Model/Adam/RNG plus episode metadata; not full simulator restore and not eligible for automatic extension/resume.')
    for key in replicas:
        _, _, _, digest = c.build_streams(reg, key)
        replicas[key]['stream_sha256'] = digest
    return reg


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    c.need(args.revision > 0 and not (c.HERE / 'launch.claimed').exists(), 'Preparation after launch refused')
    reg = registration(args.revision)
    for path in c.HERE.glob('*.py'):
        reg['source_pins'][str(path)] = c.sha(path)
    path = c.HERE / ('registration-r%d.json' % args.revision)
    c.verify_pins(reg)
    c.save(path, reg)
    cache = c.HERE / 'empty-pycache'
    if not cache.exists(): cache.mkdir()
    c.need(not list(cache.iterdir()), 'Cache must be empty before launch')
    outputs = c.HERE / 'outputs'; outputs.mkdir(exist_ok=True)
    for job in reg['jobs']:
        (outputs / job['id']).mkdir(exist_ok=True)
        c.need(not list((outputs / job['id']).iterdir()), 'Output already consumed')
    print(c.canonical(dict(registration=str(path), sha256=c.sha(path), model_or_game_construction=False,
                           claim_or_lease_mutation=False, new_seed_cohort=False)).decode())


if __name__ == '__main__':
    main()
