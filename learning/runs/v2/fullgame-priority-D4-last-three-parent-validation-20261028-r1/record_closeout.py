"""Publish the completed evaluation and development selection to the idle main ledger."""
import datetime
import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / 'fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1'
sys.path.insert(0, str(PACKAGE))
import binding as b


def main():
    state = b.read(b.MAIN_STATE)
    b.need(state['active_long_campaign'] is None, 'main training lease active')
    b.need(b.read(b.OWN_LEDGER)['active_evaluation_lease'] is None, 'evaluation lease active')
    audit = PACKAGE / 'parent-terminal-audit.json'
    b.need(b.read(audit)['status'] == 'accepted_complete_fixed_terminal60_d4_evaluation', 'audit not accepted')
    selection = b.read(HERE / 'lower-quarter-selection.json')
    proposal = HERE / 'continuation-proposal.json'
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    work = state['rl_followup_experiments']
    work.update(completed_evaluated_models=6, completed_fixed_training_models=6,
                remaining_evaluation_completed=True, remaining_evaluation_parent_audit=str(audit),
                remaining_evaluation_parent_audit_sha256=b.sha(audit),
                six_model_merge=str(PACKAGE / 'six-model-merge.json'),
                six_model_merge_sha256=b.sha(PACKAGE / 'six-model-merge.json'),
                selected_development_model=selection['selected_model'],
                lower_quarter_selection=str(HERE / 'lower-quarter-selection.json'),
                lower_quarter_selection_sha256=b.sha(HERE / 'lower-quarter-selection.json'),
                continuation_proposal=str(proposal), continuation_proposal_sha256=b.sha(proposal),
                current_launch_authorized=False, active_run_id=None, promoted=False)
    state.update(status='six_models_trained_and_evaluated_uniform2_selected_for_continuation_preparation',
                 last_update_at_utc=now, next_actions=[
                     'Prepare successor-only restoration and registration for replica-2-uniform continuation: 60 updates, unchanged reward/architecture/PPO/sampling.',
                     'Reserve fresh excluded development evaluation seeds before launch; compare continuation with its selected starting model.',
                     'Retain official parent324 and all completed evidence; D5/B/E stay closed. No training currently active.'])
    prior_sha = b.sha(b.MAIN_STATE)
    descriptor, temporary = tempfile.mkstemp(prefix='.six-model-closeout-', dir=b.MAIN_STATE.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(state, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        b.need(b.sha(b.MAIN_STATE) == prior_sha, 'main ledger changed concurrently')
        os.replace(temporary, b.MAIN_STATE)
        descriptor = os.open(b.MAIN_STATE.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    b.save(HERE / 'six-model-closeout.json', dict(
        status='all_six_training_and_evaluation_audits_accepted', at_utc=now,
        selected_development_model=selection['selected_model'], selected_q1=selection['ranking'][0]['Q1'],
        trained_models=6, evaluated_models=6, evaluation_episodes=6144,
        final_part_elapsed_seconds=b.read(PACKAGE / 'execution-exit.json')['elapsed_seconds'],
        main_lease=None, evaluation_lease=None, official_retained_parent=324,
        promoted=False, new_training_launched=False,
        source_review_tests=97, source_review_test_failures=0, source_review_test_skips=0,
        real_nondegenerate_bootstrap_reproduction=True, all_six_producer_contracts_verified=True,
        pins={str(path): b.sha(path) for path in (audit, HERE / 'lower-quarter-selection.json', proposal,
                                                 PACKAGE / 'six-model-merge.json')},
        previous_main_state_sha256=prior_sha, main_state_sha256=b.sha(b.MAIN_STATE)))
    print('six_model_closeout_recorded_no_training_launched')


if __name__ == '__main__':
    main()
