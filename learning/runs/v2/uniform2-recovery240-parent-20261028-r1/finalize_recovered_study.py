"""After recovery acceptance, qualify preserved evaluations and select across the original eleven boundaries.

Original interrupted attempt remains incomplete. Its complete saved prefix is checked independently, then combined
with accepted recovery evaluations. This makes no checkpoint eligible for official promotion or confirmation.
"""
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / 'uniform2-recovery240-luna-20261028-r1'
OLD = HERE.parent / 'uniform2-continuation600-luna-20261028-r2'
sys.path.insert(0, str(PACKAGE))
import binding as b
import metrics
import terminal


def main():
    b.need(not (HERE / 'recovered-study-result.json').exists(), 'Study result already exists; do not repeat selection.')
    accepted = b.read(PACKAGE / 'parent-terminal-audit.json')
    b.need(accepted['schema'] == b.AUDIT_SCHEMA
           and accepted['status'] == 'accepted_complete_240_update_recovery_with_5_evaluations'
           and accepted['registration_sha256'] == b.sha(PACKAGE / 'registration-final.json')
           and accepted['source_manifest_sha256'] == b.sha(PACKAGE / 'source-manifest.json')
           and accepted['raw_worker_exit_code'] == accepted['raw_observer_exit_code'] == 0
           and accepted['promoted'] is False and accepted['selection_independently_recomputed'] is True,
           'Accepted complete recovery audit required before reading scores.')
    manifest_path = PACKAGE / 'dispatch' / b.RUN_ID / 'artifact-manifest.json'
    b.need(accepted['artifact_manifest_path'] == str(manifest_path)
           and accepted['artifact_manifest_sha256'] == b.sha(manifest_path), 'Audited recovery manifest differs.')
    manifest = b.read(manifest_path)
    b.check_pins({str(PACKAGE / 'worker-output' / name): digest for name, digest in manifest.items()})
    prefix = b.read(HERE / 'original-prefix-stream-audit.json')
    b.need(prefix['status'] == 'passed_complete_saved_prefix_through360'
           and prefix['journal_sha256'] == b.sha(OLD / 'worker-output/training-events.jsonl')
           and prefix['source_sha256'] == b.sha(HERE / 'audit_original_prefix.py'), 'Original saved-prefix stream proof differs.')
    original_files = b.read(HERE / 'original-artifact-manifest.json')
    b.check_pins({str(OLD / path): digest for path, digest in original_files.items()})
    original_reg = b.read(OLD / 'registration-final.json')
    original_sha = b.sha(OLD / 'registration-final.json')
    spec = importlib.util.spec_from_file_location('original_continuation_binding', OLD / 'binding.py')
    original_binding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original_binding)
    original_identity = original_binding.identity_hash(original_binding.learner_identity(original_reg, original_sha))
    original_binding.check_owned_source()
    original_binding.check_pins(original_reg['input_pins'])
    analysis = b.frozen()['expanded_eval']
    journal = {}
    for event in terminal.rows(OLD / 'worker-output/evaluation-events.jsonl', strict=True):
        if event['kind'] != 'evaluation_episode':
            continue
        key = (event['global_update'], event['episode_index'])
        b.need(key not in journal, 'Duplicate original evaluation episode.')
        journal[key] = event
    b.need(len(journal) == 7 * 1024, 'Seven complete original evaluations required.')
    selection = metrics.Selection()
    sources = []
    original_baseline360 = None
    for update in range(0, 601, 60):
        source = OLD if update <= 360 else PACKAGE
        registration_sha = original_sha if source == OLD else b.sha(PACKAGE / 'registration-final.json')
        receipt_path = source / 'worker-output' / f'evaluation-{update:03d}.json'
        receipt = b.read(receipt_path)
        b.need(receipt['global_update'] == update and receipt['registration_sha256'] == registration_sha
               and receipt['cohort'] == 'D6' and receipt['action_mode'] == 'sampled_categorical'
               and receipt['normal_start'] is True and receipt['cutoff_enabled'] is False
               and receipt['automatic_selection'] is False and receipt['promoted'] is False,
               'Evaluation semantics or identity differs.')
        if update == 0:
            digest = original_reg['parent']['checkpoint_sha256']
            expected = original_reg['parent']['restore_fingerprints']
        else:
            checkpoint = source / 'worker-output' / f'checkpoint-global-{update:03d}.pt'
            sidecar = b.read(Path(str(checkpoint) + '.json'))
            digest = b.sha(checkpoint)
            b.need(digest == sidecar['sha256'] and not checkpoint.stat().st_mode & 0o222,
                   'Saved checkpoint bytes or immutability differs.')
            if source == OLD:
                b.need(sidecar['identity_sha256'] == original_identity and sidecar['global_update'] == update
                       and sidecar['phase_update'] == 384 + update and sidecar['cumulative_update'] == 432 + update,
                       'Original saved checkpoint lineage differs.')
            expected = dict(model=sidecar['model_fingerprint'], Adam=sidecar['optimizer_fingerprint'], RNG=sidecar['rng_fingerprint'])
        claim = b.read(source / 'worker-output' / f'evaluation-{update:03d}.claim')
        b.need(claim == dict(global_update=update, checkpoint_sha256=digest, registration_sha256=registration_sha)
               and receipt['checkpoint_sha256'] == digest, 'Evaluation checkpoint binding differs.')
        restored = receipt['learner_state_restored']
        b.need(restored['fingerprints'] == expected and restored['module_training_flags_equal'] is True,
               'Evaluation changed learner state.')
        if update:
            b.need(receipt['scratch']['model_fingerprint'] == expected['model'], 'Scratch weights differ.')
        rows = analysis.validate_full_rows(receipt['rows'], b.SEEDS)
        b.need(metrics.summarize(rows) == receipt['summary'], 'Evaluation summary differs from full rows.')
        b.need(receipt['raw_frames_including_startup'] == sum(row['gameplay_frames'] + row['startup_frames'] for row in rows),
               'Evaluation frame accounting differs.')
        if source == OLD:
            for row in rows:
                event = journal[(update, row['episode_index'])]
                b.need(event['raw'] == row['gameplay_frames'] and event['alive_frames'] == row['alive_frames']
                       and event['terminated'] == row['terminated'] and event['seed'] == row['seed'],
                       'Original evaluation row differs from its journal.')
        selection.add(update, receipt['summary'], digest)
        sources.append(dict(global_update=update, receipt_path=str(receipt_path), receipt_sha256=b.sha(receipt_path)))
        if update == 360:
            original_baseline360 = receipt['summary']
    repeated = b.read(PACKAGE / 'worker-output/evaluation-360.json')
    b.save(HERE / 'recovered-study-result.json', dict(schema='uniform2_recovered_continuation600_study_v1',
        status='accepted_saved_prefix_plus_independently_audited_recovery_development_comparison',
        original_attempt_status='interrupted_incomplete_not_qualified_as_a_complete_campaign',
        original_prefix_stream_audit_sha256=b.sha(HERE / 'original-prefix-stream-audit.json'),
        recovery_terminal_audit_sha256=b.sha(PACKAGE / 'parent-terminal-audit.json'),
        episode_count_used_for_selection=11 * 1024, sources=sources, **selection.report(),
        baseline360_repeat_summary_equal=repeated['summary'] == original_baseline360,
        baseline360_choice='Original baseline360 is fixed for merged selection; the repeat is not an extra candidate.',
        attempted_completed_updates=640, effective_continuation_updates=600, lost_completed_updates=40,
        attempted_completed_updates_definition='Sum of journaled completed updates; unjournaled original update401 work is unknown.',
        uncertainty='One recovered training trajectory on repeatedly used development seeds, not confirmation.',
        official_parent324_promotion=False, automatic_selection=False, promoted=False, training_eligible=False))
    print('recovered_study_eleven_boundaries_audited_no_promotion')


if __name__ == '__main__':
    main()
