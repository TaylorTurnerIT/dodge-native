"""Prepare the explicitly authorized fresh restart; no games or ledger writes."""
import argparse
import copy

import common as c


def registration(revision):
    predecessor = c.HERE.parent / 'k1-horizon-screen-20261030-r1'
    path = predecessor / 'registration-r2.json'
    c.need(c.sha(path) == '508025d147405589589f6f9bad10f7865156660e5e72a51619a681a24407ef86',
           'Original registration differs')
    old = c.read(path)
    reg = copy.deepcopy(old)
    reg.update(run_id='K1-horizon-screen-20261030-r2', revision=revision,
               package=str(c.HERE), record='DODGE-051', source_pins={})
    reg['expected_lease'] = dict(kind='K1_horizon_training_screen', run_id=reg['run_id'],
        package=str(c.HERE), owner_token='horizon051-20261030-single-claim-r2', promoted=False)
    reg['predecessor'] = dict(package=str(predecessor), registration_path=str(path),
        registration_sha256=c.sha(path), expected_lease=old['expected_lease'],
        disposition_path=str(predecessor / 'power-failure-disposition.json'))
    # Pin the failed attempt without copying its mutable controls or trained weights.
    reg['input_pins'].update(old['source_pins'])
    for name in ['registration-r2.json', 'authority.json', 'launch.claimed', 'first-failure.json',
                 'power-failure-disposition.json', 'outputs/r1-matched/launch.json',
                 'outputs/r1-matched/worker.claimed', 'outputs/r1-matched/exit.json',
                 'outputs/r1-matched/first-failure.json', 'outputs/r1-matched/prefix-qualification.json']:
        f = predecessor / name
        reg['input_pins'][str(f)] = c.sha(f)
    for artifact in c.read(reg['predecessor']['disposition_path'])['preserved_artifacts']:
        f = c.HERE.parents[3] / artifact['path']
        c.need(c.sha(f) == artifact['sha256'], 'Failed attempt evidence changed')
        reg['input_pins'][str(f)] = artifact['sha256']
    reg['restart_policy'] = ('Fresh checkpoint420 model/Adam restores; same registered four jobs, '
        'RNG streams, consumed512 pool and limits. Prior partial work remains failure evidence, '
        'excluded from this attempt. No partial snapshot restore or further retry.')
    return reg


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    c.need(args.revision > 0 and not (c.HERE / 'launch.claimed').exists(), 'Preparation after launch refused')
    reg = registration(args.revision)
    for path in c.HERE.glob('*.py'):
        reg['source_pins'][str(path)] = c.sha(path)
    c.verify_pins(reg)
    path = c.HERE / ('registration-r%d.json' % args.revision)
    c.save(path, reg)
    cache = c.HERE / 'empty-pycache'
    if not cache.exists(): cache.mkdir()
    c.need(not list(cache.iterdir()), 'Cache must be empty before launch')
    outputs = c.HERE / 'outputs'; outputs.mkdir(exist_ok=True)
    for job in reg['jobs']:
        out = outputs / job['id']; out.mkdir(exist_ok=True)
        c.need(not list(out.iterdir()), 'Output already consumed')
    print(c.canonical(dict(registration=str(path), sha256=c.sha(path),
        claim_or_lease_mutation=False, new_seed_cohort=False)).decode())


if __name__ == '__main__':
    main()
