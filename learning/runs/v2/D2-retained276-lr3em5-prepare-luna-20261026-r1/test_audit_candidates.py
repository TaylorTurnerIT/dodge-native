"""CPU-only auditor contract tests; synthetic candidate rows are relabelled fixtures, never run results."""
import copy
import unittest
import torch

import audit_candidates as a

torch.set_num_threads(4)
assert torch.get_num_threads() <= 4

_CACHE = {}


def ctx():
    if not _CACHE:
        runner, reg, config = a.load_frozen(enforce_lease=False)
        ckpt, gate, identity_hash = a.import_runtime(reg)
        _CACHE.update(a.build_context(runner, reg, config, ckpt, gate, identity_hash, [], [], runner._VERIFIED_TRANSITION))
    return _CACHE


def entry_state(c):
    parent, reg = c['parent'], c['reg']
    identity = {'version':'teacher_identity_v3','run_id':a.RUN_ID,'phase':'D2',
        'phase_update_start':276,'phase_update_end':336,'run_seed':a.RUN_SEED,'config':c['config'],
        'parent_checkpoint_sha256':a.PARENT_SHA,'parent_terminal_receipt_sha256':a.PARENT_RECEIPT_SHA,
        'parent_config_sha256':a.PARENT_CONFIG_SHA,'lr_transition':reg['arm_transition'],
        'policy_sha256':a.POLICY_SHA,'registration_sha256':a.REG_SHA,
        'architecture':parent['identity']['architecture']}
    opt=copy.deepcopy(parent['optimizer'])
    for group in opt['param_groups']: group['lr']=a.LR_ARM
    wall=10.0
    return {'version':'teacher_checkpoint_v1','schema':'d2_training_v3_checkpoint_v1','resume_mode':'fresh_env',
        'tag':'candidate','phase':'D2','eligibility_status':'provisional_pending_parent_terminal_receipt',
        'training_eligible':False,'promoted':False,'parent_sha256':a.PARENT_SHA,'identity':identity,
        'identity_sha256':c['identity_hash'](identity),'config_sha256':a.CONFIG_SHA,'policy_sha256':a.POLICY_SHA,
        'native_sha256':a.NEW_NATIVE_SHA,'run_seed':a.RUN_SEED,'runtime_sha256':reg['runtime_sha256'],
        'registration_sha256':a.REG_SHA,'model':copy.deepcopy(parent['model']),'optimizer':opt,'rng':copy.deepcopy(parent['rng']),
        'counters':dict(a.ENTRY_ZERO),'inherited_counters':dict(parent['cumulative_counters']),
        'cumulative_counters':dict(parent['cumulative_counters']),'phase_update':276,'local_update':0,
        'selected_parent_checkpoint_trajectory_baseline_seconds':a.SELECTED_TRAJECTORY_BASELINE,
        'parent_completed_campaign_cost_baseline_seconds':a.CAMPAIGN_COST_BASELINE,
        'current_iteration_observed_outer_seconds':wall,
        'cumulative_selected_checkpoint_trajectory_wall_seconds':a.SELECTED_TRAJECTORY_BASELINE+wall,
        'cumulative_successful_ancestor_and_completed_campaign_cost_seconds':a.CAMPAIGN_COST_BASELINE+wall,
        'update_progress':{'complete':True,'in_update':False,'completed_updates':0},
        'next_episode_indices':list(parent['next_episode_indices']),
        'abandoned_current_episodes':copy.deepcopy(parent['abandoned_current_episodes']),
        'parent_abandoned_current_episodes':copy.deepcopy(parent['abandoned_current_episodes']),
        'parent_run_id':a.PARENT_RUN_ID,'parent_registration_sha256':a.PARENT_REGISTRATION_SHA,
        'parent_checkpoint_sha256':a.PARENT_SHA}


def fixture_metrics(c):
    path=a.PARENT_RUN/'training-metrics.jsonl'
    source,_=a.parse_journal(a.read_stable(path),strict=True)
    rows=[]; steps=0
    for local,old in enumerate(source[:60],1):
        value=copy.deepcopy(old['metrics']); steps += value['optimizer_steps']
        rows.append({'phase_update':276+local,'local_update':local,
            'counters':{'updates':local,'optimizer_steps':steps,'environment_decisions':local*a.DECISIONS_PER_UPDATE,
                        'raw_frames':local},
            'update_progress':{'completed_updates':local,'complete':True,'in_update':False},'metrics':value})
    return rows


def entry_eval_fixture():
    cert,_=a.stable_json(a.PARENT_RUN/'development-000276.json')
    rows,_=a.parse_journal(a.read_stable(a.PARENT_RUN/'development-000276.jsonl'),strict=True)
    return cert,rows


def mutate_tensor(tree):
    if isinstance(tree,dict):
        return any(mutate_tensor(value) for value in tree.values())
    if isinstance(tree,(list,tuple)):
        return any(mutate_tensor(value) for value in tree)
    if hasattr(tree,'is_floating_point') and tree.is_floating_point() and tree.numel():
        tree.reshape(-1)[0].add_(1); return True
    if hasattr(tree,'dtype') and hasattr(tree,'reshape') and tree.numel():
        tree.reshape(-1)[0]=tree.reshape(-1)[0] ^ 1; return True
    return False


class FrozenBindings(unittest.TestCase):
    def test_registration_pins_and_six_candidate_boundaries(self):
        c=ctx(); r=c['runner']
        self.assertEqual(a.sha_file(a.REG_PATH),a.REG_SHA)
        self.assertEqual((a.PHASE_START,a.PHASE_END),(276,336))
        self.assertEqual(a.UPDATES,(276,288,300,312,324,336))
        self.assertEqual(a.NEW_UPDATES,60)
        self.assertEqual(r.EXPECTED_TOTAL,384)
        self.assertEqual(a.MAX_OPTIMIZER_STEPS,7680)
        self.assertEqual(a.expected_outputs(),c['reg']['expected_outputs'])
        self.assertEqual(c['reg']['run_seed'],3791628420)

    def test_real_parent_cpu_checkpoint_and_external_receipt_validate(self):
        c=ctx()
        self.assertEqual(c['parent']['phase_update'],276)
        self.assertEqual(c['parent']['cumulative_counters'],{'updates':324,'optimizer_steps':40352,
            'environment_decisions':5308416,'raw_frames':21202529})
        self.assertEqual(c['runner'].fingerprint(c['parent']['optimizer']),
            '57d2d1b2e38843dcc047818f0eef490095056024f7dd34720a1ca61b8b614098')

    def test_entry_transition_excludes_only_group_lr(self):
        c=ctx(); state=entry_state(c); a.validate_state_identity(c,276,state); a.validate_entry_state(c,state)
        parent=c['parent']['optimizer']; eff=state['optimizer']; helper=c['transition_helper']
        self.assertEqual(helper.fingerprint(helper.without_group_lr(parent)),
                         helper.fingerprint(helper.without_group_lr(eff)))
        self.assertEqual([g['lr'] for g in eff['param_groups']],[3e-5]*len(eff['param_groups']))

    def test_all_six_boundary_state_fixtures_validate(self):
        c=ctx(); rows=fixture_metrics(c); c['metrics']=rows
        c['rows_by_phase']={row['phase_update']:[row] for row in rows}
        for update in a.UPDATES:
            local=update-276; state=entry_state(c)
            if local:
                row=rows[local-1]; state['phase_update']=update; state['local_update']=local
                state['counters']=dict(row['counters']); state['update_progress']=dict(row['update_progress'])
                state['cumulative_counters']=c['runner'].continuation_cumulative_counters(c['parent']['cumulative_counters'],state['counters'])
                state['current_iteration_observed_outer_seconds']=20.0
                state['cumulative_selected_checkpoint_trajectory_wall_seconds']=a.SELECTED_TRAJECTORY_BASELINE+20
                state['cumulative_successful_ancestor_and_completed_campaign_cost_seconds']=a.CAMPAIGN_COST_BASELINE+20
            a.validate_state_identity(c,update,state)

    def test_candidate_certificate_validator_at_all_six_boundaries(self):
        c=ctx(); base,rows=entry_eval_fixture()
        for update in a.UPDATES:
            cert=copy.deepcopy(base); cert['phase_update']=update; cert['local_update']=update-276
            cert['checkpoint']=f'checkpoint-{update:06d}-candidate.pt'; cert['checkpoint_sha256']='a'*64
            side={'checkpoint_sha256':'a'*64,'eligibility_status':'provisional_pending_parent_terminal_receipt',
                  'training_eligible':False,'promoted':False}
            a.validate_certificate(c,update,cert,side,rows,cert['checkpoint'],'a'*64)

    def test_wrong_lr_moments_rng_model_config_transition_receipt_and_cost_reject(self):
        c=ctx(); base=entry_state(c)
        bad=copy.deepcopy(base); bad['optimizer']['param_groups'][0]['lr']=1e-4
        with self.assertRaisesRegex(a.AuditError,'Saved optimizer LR'): a.validate_entry_state(c,bad)
        bad=copy.deepcopy(base); self.assertTrue(mutate_tensor(bad['optimizer']['state']))
        with self.assertRaisesRegex(a.AuditError,'Entry Adam'): a.validate_entry_state(c,bad)
        bad=copy.deepcopy(base); bad['rng']['torch_cpu'][0]=bad['rng']['torch_cpu'][0] ^ 1
        with self.assertRaisesRegex(a.AuditError,'Entry model or RNG'): a.validate_entry_state(c,bad)
        bad=copy.deepcopy(base); self.assertTrue(mutate_tensor(bad['model']))
        with self.assertRaisesRegex(a.AuditError,'Entry model or RNG'): a.validate_entry_state(c,bad)
        helper=c['transition_helper']
        badconfig=copy.deepcopy(c['config']); badconfig['ppo']['target_kl']+=.01
        with self.assertRaisesRegex(ValueError,'outside ppo.learning_rate'):
            helper.validate_config_transition(a.json.loads(a.read_stable(c['reg']['parent_config_path'])),badconfig)
        record={'parent_checkpoint_sha256':a.PARENT_SHA,'parent_receipt_sha256':a.PARENT_RECEIPT_SHA,
            'parent_config_sha256':a.PARENT_CONFIG_SHA,'arm_config_sha256':a.CONFIG_SHA,
            'helper_sha256':helper.sha256_file(a.PREP/'lr_transition.py'),'changed_fields':['optimizer.param_groups[*].lr'],
            'non_lr_fields_changed':[],'parent_lr':a.LR_PARENT,'effective_lr':a.LR_ARM,
            'actual_group_lr_delta':[{'index':0,'before':a.LR_PARENT,'after':a.LR_ARM}],
            'parent_optimizer_fingerprint':'0'*64,'parent_optimizer_fingerprint_excluding_lr':'0'*64,
            'effective_optimizer_fingerprint_excluding_lr':'0'*64,'effective_optimizer_fingerprint':'0'*64}
        with self.assertRaisesRegex(a.AuditError,'fingerprint'):
            a.validate_lr_transition_record(c['runner'],helper,record,c['parent'],
                {'components':{'Adam':{'restored_sha256':'0'*64}}},base)
        self.assertNotEqual(a.SELECTED_TRAJECTORY_BASELINE,a.CAMPAIGN_COST_BASELINE)
        self.assertEqual(a.SELECTED_TRAJECTORY_BASELINE,4760.062404125177)
        self.assertEqual(a.CAMPAIGN_COST_BASELINE,7118.78208862512)

    def test_missing_stale_progress_metrics_and_gradient_schema_reject(self):
        c=ctx(); rows=fixture_metrics(c)
        for row in rows: row['phase_update']-=276
        with self.assertRaisesRegex(a.AuditError,'contiguous'):
            a.validate_metric_rows(c['runner'],rows,60)
        rows=fixture_metrics(c); del rows[0]['update_progress']
        with self.assertRaises((KeyError,ValueError,a.AuditError)): a.validate_metric_rows(c['runner'],rows,60)
        rows=fixture_metrics(c); del rows[0]['metrics']['gradient_alignment_diagnostics']
        with self.assertRaises((KeyError,ValueError,a.AuditError)): a.validate_metric_rows(c['runner'],rows,60)
        rows=fixture_metrics(c); rows[0]['metrics']['gradient_alignment_diagnostics']={'wrong_schema':True}
        with self.assertRaises((KeyError,ValueError,a.AuditError)): a.validate_metric_rows(c['runner'],rows,60)

    def test_score_does_not_select_and_ties_keep_prior(self):
        baseline=a.BASELINE_MEAN_ALIVE
        self.assertIsNone(a.choose_best({288:baseline,300:baseline-1}))
        self.assertEqual(a.choose_best({288:baseline+1,300:baseline+5,312:baseline+5}),300)
        self.assertEqual(a.retained_best([(288,baseline+5),(300,baseline+5)]),288)


if __name__=='__main__': unittest.main()
