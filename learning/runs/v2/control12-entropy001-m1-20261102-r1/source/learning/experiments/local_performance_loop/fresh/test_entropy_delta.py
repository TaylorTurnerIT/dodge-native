"""CPU-only contract checks; no production seed lookup or runtime import."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import common as c
from seed_bank import specification
from seed_stream import StreamSpec, seed_for


class EntropyDelta(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[4]
        self.prior = c.read(root/'learning/runs/v2/fresh-control12-k1-m1-20261102-r2/config.json')
        self.recipe = c.read(root/'learning/runs/v2/performance-loop-20261101-r1/config.json')
        self.reg = copy.deepcopy(self.prior)
        self.reg['run_id'] = 'synthetic-successor'
        self.reg['objective_delta'] = dict(parameter='ent_coef', before=.01, after=.001, schedule='constant')
        self.reg['ppo']['ent_coef'] = .001
        self.reg['fresh_stream']['role'] = 'exposed_training_replay_unique_within_trajectory'
        self.reg['fresh_stream']['replay'] = dict(campaign_run_id=self.prior['run_id'])

    def test_only_declared_entropy_delta_passes_recipe_gate(self):
        c.validate_shape(self.reg, self.recipe)
        for key,value in [('learning_rate',1e-5),('ent_coef',.002),('reward_scale',1),('target_kl',.02)]:
            changed=copy.deepcopy(self.reg);changed['ppo'][key]=value
            with self.assertRaises(ValueError):c.validate_shape(changed,self.recipe)
        changed=copy.deepcopy(self.reg);changed['objective_delta']['schedule']='decay'
        with self.assertRaises(ValueError):c.validate_shape(changed,self.recipe)
        changed=copy.deepcopy(self.reg);del changed['objective_delta']
        with self.assertRaises(ValueError):c.validate_shape(changed,self.recipe)

    def test_existing_original_profile_stays_valid(self):
        c.validate_shape(self.prior,self.recipe)
        changed=copy.deepcopy(self.reg);changed['total_seconds']=7200
        with self.assertRaises(ValueError):c.validate_shape(changed,self.recipe)

    def test_replay_requires_exact_science_and_accepted_released_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            def save(name,value):
                path=tmp/name;path.write_text(json.dumps(value));return str(path),c.sha(path)
            cp,ch=save('config.json',self.prior)
            ap,ah=save('audit.json',dict(status='accepted_local_control_continuation',record='DODGE-073',registration_sha256=ch))
            rp,rh=save('release.json',dict(accepted_audit_sha256=ah,lease_value_after_release=None))
            reg=copy.deepcopy(self.reg);replay=reg['fresh_stream']['replay']
            replay.update(config_path=cp,config_sha256=ch,audit_path=ap,release_path=rp)
            reg['input_pins'].update({cp:ch,ap:ah,rp:rh})
            c.validate_training_replay(reg)
            for key,value in [('evaluation_controller_domain','other'),('replicas',{}),('warmstart',{}),('policy',{})]:
                changed=copy.deepcopy(reg);changed[key]=value
                with self.assertRaises(ValueError):c.validate_training_replay(changed)
            for key,value in [('role','globally_fresh'),('stream_identity','0'*64),('bank_episodes_per_slot',99)]:
                changed=copy.deepcopy(reg);changed['fresh_stream'][key]=value
                with self.assertRaises(ValueError):c.validate_training_replay(changed)
            changed=copy.deepcopy(reg);changed['fresh_stream']['replay']['campaign_run_id']='other'
            with self.assertRaises(ValueError):c.validate_training_replay(changed)
            changed=copy.deepcopy(reg);changed['input_pins'][ap]='0'*64
            with self.assertRaises(ValueError):c.validate_training_replay(changed)
            Path(rp).write_text(json.dumps(dict(accepted_audit_sha256=ah,lease_value_after_release={'held':True})))
            with self.assertRaises(ValueError):c.validate_training_replay(reg)

    def test_spec_uses_bound_prior_campaign_without_looking_up_seeds(self):
        history=list(range(1000,190743));pool=dict(seeds=[dict(seed=i) for i in range(200000,200512)])
        registry=dict(future_training_exclusion_ranges=[[300000,300010]])
        def fixture(binding):
            if binding==self.reg['fresh_stream']['registry']:return registry
            if binding==self.reg['fresh_stream']['history']:return dict(sorted_unique_seed_values=history)
            return pool
        captured=[]
        def build(**kwargs):
            captured.append(kwargs);return type('Spec',(),dict(identity=self.reg['fresh_stream']['stream_identity']))()
        with patch('seed_bank.read_bound',side_effect=fixture),patch('seed_bank.StreamSpec',side_effect=build):
            specification(self.reg)
        self.assertEqual(captured[0]['campaign'],self.prior['run_id'])
        # Toy-domain lookup proves replay determinism, never touches the registered stream.
        a=StreamSpec('toy-prior','one',2,'a'*64,bits=8)
        b=StreamSpec('toy-prior','one',2,'a'*64,bits=8)
        self.assertEqual([seed_for(a,0,i) for i in range(5)],[seed_for(b,0,i) for i in range(5)])


if __name__=='__main__':unittest.main()
