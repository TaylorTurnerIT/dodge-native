"""Parent-owned validation and acceptance of the unchanged, reviewed last-three evaluator."""
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / 'fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1'
sys.path.insert(0, str(PACKAGE))
import binding as b
import merge
import finalize_registration


def common_contract():
    first = b.read(b.FIRST_PART / 'registration-final.json')
    last = b.read(PACKAGE / 'registration-draft.json')
    policies = first['policies'] + last['policies']
    fields = ('source_manifest_sha256', 'runtime_manifest_sha256', 'runtime_root', 'runtime_versions',
              'input_manifest_sha256', 'interpreter', 'training_pool_path', 'training_pool_file_sha256',
              'training_pool_sha256', 'training_pool_role', 'parent_checkpoint_sha256',
              'parent_receipt_sha256', 'expected_parent_fingerprints', 'shared_config', 'ppo', 'schedule',
              'exclusion_union', 'backend', 'episodes_per_slot', 'priority')
    registrations = [b.read(p['producer']['registration_path']) for p in policies]
    common = {key: registrations[0][key] for key in fields}
    for registration in registrations:
        b.need({key: registration[key] for key in fields} == common, 'producer common contract differs')
    for replica in (1, 2, 3):
        pair = [r for r in registrations if r['replica'] == replica]
        b.need(len(pair) == 2 and {r['arm'] for r in pair} == set(b.ARMS), 'matched pair missing')
        b.need(pair[0]['vector'] == pair[1]['vector'], 'within-pair training randomness differs')
    identities = [merge.verify_producer(p) for p in policies]
    b.need(len({p['checkpoint_sha256'] for p in identities}) == 6, 'checkpoint identities overlap')
    b.need(b.sha(common['training_pool_path']) == common['training_pool_file_sha256'], 'training pool drift')
    pins = {p['producer']['registration_path']: b.sha(p['producer']['registration_path']) for p in policies}
    pins.update({p['producer']['audit_path']: b.sha(p['producer']['audit_path']) for p in policies})
    pins[common['training_pool_path']] = common['training_pool_file_sha256']
    return dict(status='passed_all_six_common_training_contract_and_producer_chains', common=common,
                producer_identities=identities, pins=pins, all_six_audits_verified=True,
                checkpoint_bytes_rehashed=True, matched_pair_vectors_equal=True)


def main():
    b.need(b.sha(PACKAGE / 'source-manifest.json') ==
           '31a9c03e2e2524cbd522a44312923b021d0a3df20c596e1c7e14217ce3d568d4', 'reviewed source drift')
    b.need(b.sha(PACKAGE / 'registration-draft.json') ==
           '2ee3b511ed1cb2d39f2993e2e8f71dcded30a251ffbfb0bad3d3cd31f4bea87b', 'reviewed draft drift')
    contract = common_contract()
    b.save(HERE / 'common-training-contract.json', contract)
    first = merge.verify_part(b.FIRST_PART, b.FIRST_PART_POLICIES, pins=b.FIRST_PART_PINS)
    first_rows, stored = merge.load_rows(first)
    rows = dict(first_rows)
    for j, name in enumerate(b.POLICIES):
        rows[name] = [dict(seed=seed, alive_frames=75 + ((i * (17 + j * 6) + i*i) % (4500 + j*300)))
                      for i, seed in enumerate(b.SEEDS)]
    intervals = merge.bootstrap(rows, b.BOOTSTRAP)
    label = 'replica-1-priority_minus_uniform'
    expected = stored['paired_conditional_seed_intervals']['comparisons'][label]
    b.need(intervals[label]['performance'] == expected['performance'], 'real first-pair performance CI differs')
    b.need(intervals[label]['milestone_rate_differences'] == expected['milestone_rate_differences'],
           'real first-pair milestone CI differs')
    widths = {key: value['high'] - value['low'] for key, value in intervals[label]['performance'].items()}
    b.need(all(width > 0 for width in widths.values()), 'real bootstrap intervals degenerate')
    merge.check_against_stored(intervals, stored, {'paired_conditional_seed_intervals': {
        'comparisons': {'replica-3-priority_minus_uniform': intervals['replica-3-priority_minus_uniform']}}})
    b.save(HERE / 'nondegenerate-bootstrap-check.json', dict(
        status='passed_real_first_pair_nondegenerate_interval_reproduction', performance_widths=widths,
        first_comparison_sha256=first['comparison_sha'], bootstrap=b.BOOTSTRAP,
        synthetic_last_three=True, new_games=0, limitation='Last-pair real interval reproduction remains a final-merge check.'))
    review = b.V2 / 'fullgame-priority-D4-last-three-review-haiku-20261028-r1/review.json'
    b.save(HERE / 'review-dispositions.json', dict(status='accepted_no_blocking_findings',
        review_path=str(review), review_sha256=b.sha(review), dispositions={
            'F1': 'All six producer registrations, common source/runtime/interpreter/pool/parent/PPO/schedule and paired RNG vectors verified externally.',
            'F2': 'Real audited first-pair rows reproduce non-degenerate stored intervals; final merge checks both actual pairs.',
            'F3': 'All six producer chains and checkpoint bytes independently verified; no missing audit skipped.',
            'F4': 'Sealed preparation README is historical. All six training audits now accepted, draft exists, 97 tests passed without skips.',
            'F5': '7352-second work cap accepted; first part completed in 585.3241 seconds under shared GPU load.'},
        source_unchanged=True, all_training_finished=True, official_parent=324, promotion=False))
    b.need(b.read(b.MAIN_STATE)['active_long_campaign'] is None, 'training lease not clear')
    source_acceptance = PACKAGE / 'source-acceptance.json'
    b.save(source_acceptance, dict(status='accepted_source_review_only',
        source_manifest_sha256=b.sha(PACKAGE / 'source-manifest.json'), review_sha256=b.sha(review),
        parent_dispositions_sha256=b.sha(HERE / 'review-dispositions.json')))
    draft = b.read(PACKAGE / 'registration-draft.json')
    calibration = HERE / 'calibration-acceptance.json'
    b.save(calibration, dict(status='accepted_parent_resource_calibration', limits=draft['limits'],
        work_seconds=7352, cleanup_seconds=10, postflight_seconds=120, total_seconds=7482,
        rss_bytes=6*1024**3, mps_bytes=6*1024**3, episodes=3072, constructors=3072,
        raw_frames=55335936, native_steps=55296000, resets=0, retries=0,
        basis=draft['calibration'], concurrent_training=False))
    final = finalize_registration.finalize(PACKAGE / 'registration-draft.json',
        b.sha(PACKAGE / 'registration-draft.json'), calibration, b.sha(calibration))
    b.validate_static(final)
    b.save(PACKAGE / 'registration-final.json', final)
    scope = b.V2 / 'fullgame-priority-three-run-execution-parent-20261028-r1/last-three-evaluation-scope-acceptance.json'
    files = [review, HERE / 'common-training-contract.json', HERE / 'nondegenerate-bootstrap-check.json',
             HERE / 'review-dispositions.json', HERE / 'test-receipt.json', Path(__file__).resolve(),
             source_acceptance, calibration, PACKAGE / 'registration-final.json', scope]
    pins = {str(path): b.sha(path) for path in files}
    pins.update(contract['pins'])
    b.save(PACKAGE / 'gate-acceptance.json', b.approval_document(
        b.sha(PACKAGE / 'registration-final.json'), b.sha(PACKAGE / 'source-manifest.json'), pins))
    print(json.dumps(dict(status='ready_not_launched', registration_sha256=b.sha(PACKAGE / 'registration-final.json'),
        gate_sha256=b.sha(PACKAGE / 'gate-acceptance.json'), source_acceptance_sha256=b.sha(source_acceptance))))


if __name__ == '__main__':
    main()
