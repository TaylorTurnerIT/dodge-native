"""Read-only exact seed-stream audit for registered equal-frame arms."""
from __future__ import annotations
import json
import binding as b
import seeds


def audit(registration):
    reg=b.read(registration); b.validate_static(reg,check_streams=True)
    pool,seeds_by_slot,components=seeds.build_registered_streams(reg)
    report=dict(schema='one_frame_training_comparison_stream_audit_v1',run_id=reg['run_id'],
        training_pool_sha256=pool['pool_sha256'],slots=len(seeds_by_slot),
        capacity_per_slot=len(seeds_by_slot[0]),all_components_uniform=all(
            value=='uniform' for row in components for value in row),
        identical_for_both_arms=True,initial_episode_indices=[0]*len(seeds_by_slot),
        evaluation_ranges_excluded=reg['exclusion_union'],launch_authority=False,
        no_seeds_consumed=True)
    b.need(report['all_components_uniform'],'nonuniform training stream component')
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True)
    args=parser.parse_args();print(json.dumps(audit(args.registration),sort_keys=True))
