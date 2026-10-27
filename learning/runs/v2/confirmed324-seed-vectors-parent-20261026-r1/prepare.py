"""Rebind the existing stdlib seed derivation to the confirmed parent; never apply seeds."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OWN = Path(__file__).resolve().parent
STUDY = 'paired-lr-confirmed324-20261026-r1'
SOURCE = ROOT / 'learning/runs/v2/PPO-RNG-seed-vectors-parent-20261026-r2/stdlibderive.py'
PARENT = ROOT / 'learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json'
PARENT_SHA = '76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


def prepare():
    raw_parent = PARENT.read_bytes()
    assert digest(raw_parent) == PARENT_SHA
    parent = json.loads(raw_parent)
    assert parent['candidate_phase_update'] == 324
    assert parent['candidate_cumulative_counters']['updates'] == 372
    indices = parent['next_episode_indices']
    assert len(indices) == 64 and all(type(index) is int and index >= 0 for index in indices)
    raw_source = SOURCE.read_bytes()
    module = type(sys)('inert_confirmed324_stdlib_seed_derivation')
    module.__file__ = str(SOURCE)
    exec(compile(raw_source, str(SOURCE), 'exec'), module.__dict__)
    module.STUDY_ID = STUDY
    module.PARENT_RECEIPT_SHA256 = PARENT_SHA
    module.PARENT_NEXT_EPISODE_INDICES = tuple(indices)
    module.PRIOR_MASTER_SEEDS = tuple(sorted(set(module.PRIOR_MASTER_SEEDS) | {5562881586070242562}))
    proposal = module.build_vectors()
    module.validate(proposal['vectors'])
    for row in proposal['vectors']:
        assert row['env_control']['episode_indices'] == indices
        assert row['env_control']['reserved_hits'] == 0
        assert row['vector_sha256'] == digest(module.canonical({
            'study_id': STUDY, 'replica': row['replica'], 'seeds': row['seeds']}))
    proposal['schema'] = 'd2_layerb_proposed_rng_seed_vectors_v3'
    proposal['parent'] = {'phase_update': 324, 'cumulative_update': 372,
                          'checkpoint_sha256': parent['checkpoint_sha256'],
                          'integrity_receipt_path': str(PARENT), 'integrity_receipt_sha256': PARENT_SHA,
                          'next_episode_indices': indices}
    proposal['derivation']['source_path'] = str(SOURCE)
    proposal['derivation']['source_sha256'] = digest(raw_source)
    proposal['derivation']['rebind'] = 'same algorithm; new study ID and confirmed324 episode indices'
    write_new(OWN / 'seed-vectors.json', proposal)
    write_new(OWN / 'receipt.json', {
        'schema': 'parent_confirmed324_seed_vector_preparation_v1',
        'status': 'stdlib_controls_pass_proposal_only', 'study_id': STUDY,
        'interpreter': sys.executable, 'python': sys.version,
        'derivation_source_sha256': digest(raw_source), 'source_sha256': digest(Path(__file__).read_bytes()),
        'proposal_sha256': digest((OWN / 'seed-vectors.json').read_bytes()),
        'pairs': 3, 'vectors': 3, 'first_episode_slots_per_vector': 64,
        'parent_integrity_receipt_sha256': PARENT_SHA, 'seeds_reserved': False,
        'real_rng_reference': 'pending_notrun', 'MPS_or_training_run': False,
        'limits': ['Stdlib projection only; native environment controls remain unmeasured.',
                   'The five-range exclusion union must be installed before future environment construction.',
                   'Three exploratory paired training replicas do not establish a confirmatory method comparison.']})
    print('Three vectors derived for confirmed324; 192 first-slot seeds avoid the five reserved ranges. No seeds applied.')


if __name__ == '__main__':
    prepare()
