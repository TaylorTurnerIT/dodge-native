"""Read-only source preparation check. Never imports a model/native runtime."""
import argparse
import copy
import json
from pathlib import Path
import sys
import common as c
from seed_bank import specification


def check(path):
    path=Path(path); manifest=c.read(path/'candidate-bindings.json')
    for item in manifest['local_pins']:
        c.need(c.sha(item['path']) == item['sha256'], 'Source/preparation input changed: '+item['path'])
    reg=c.read(path/'candidate-config.json')
    c.need(c.sha(path/'candidate-config.json') == manifest['candidate_sha256'], 'Candidate binding differs')
    c.need(not reg['execution_authorized'] and not reg['training_authorized'] and not reg['fresh_games_authorized'],
           'This preparation cannot self-authorize fresh games')
    c.validate_shape(reg, c.read(manifest['source_recipe_local']))
    c.validate_baseline_binding(reg, c.read(manifest['baseline_source_config_local']))
    localized=copy.deepcopy(reg)
    for key in ['registry','history','pool']:
        localized['fresh_stream'][key]['path']=manifest['lineage_local_paths'][key]
    spec=specification(localized)  # Builds exclusion metadata only; no seed_for.
    for entry in manifest['reused_source_files']:
        c.need(c.sha(entry['path']) == entry['sha256'], 'Reused component source changed')
    c.need(not any(m == 'torch' or m == 'dodge_rl' or m.startswith('dodge_rl.') for m in sys.modules),
           'Source check loaded a model/native package')
    return dict(status='source_candidate_checked_not_execution_authorized',
        candidate_sha256=manifest['candidate_sha256'],fresh_stream_identity=spec.identity,
        remaining_domain_capacity=spec.capacity,source_bindings_checked=len(manifest['local_pins']),
        production_seed_lookups=0,native_games=0,checkpoint_loads=0,optimizer_steps=0,
        MPS_work=False,lease_operations=0,heldout_outcomes_read=False,
        minimum_remaining_gate='Explicit execution disposition for this exact fresh-games choice, exact delta review/final attempt binding; counted first-two qualification occurs inside that authorized attempt, not now.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--packet',required=True)
    args=parser.parse_args();print(json.dumps(check(args.packet),indent=2,sort_keys=True))
