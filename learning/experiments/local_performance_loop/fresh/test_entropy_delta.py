"""CPU-only contract checks; registered stream identity uses real bound metadata."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import common as c
from seed_bank import specification
from seed_stream import StreamSpec, seed_for


class EntropyDelta(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[4]
        self.prior = c.read(self.root/'learning/runs/v2/fresh-control12-k1-m1-20261102-r2/config.json')
        self.recipe = c.read(self.root/'learning/runs/v2/performance-loop-20261101-r1/config.json')
        self.reg = copy.deepcopy(self.prior)
        self.reg['run_id'] = 'control12-entropy001-m1-20261102-r1'
        self.reg['record'] = 'DODGE-074'
        self.reg['objective_delta'] = dict(parameter='ent_coef', before=.01, after=.001, schedule='constant')
        self.reg['ppo']['ent_coef'] = .001
        self.reg['fresh_stream']['role'] = 'exposed_training_replay_unique_within_trajectory'
        self.reg['fresh_stream']['replay'] = dict(source_run_id=self.prior['run_id'],
            seed_campaign=self.prior['fresh_stream']['campaign'])

    def test_only_declared_entropy_delta_passes_recipe_gate(self):
        c.validate_shape(self.reg, self.recipe)
        for key,value in [('learning_rate',1e-5),('ent_coef',.002),('reward_scale',1),('target_kl',.02)]:
            changed=copy.deepcopy(self.reg);changed['ppo'][key]=value
            with self.assertRaises(ValueError):c.validate_shape(changed, self.recipe)
        changed=copy.deepcopy(self.reg);changed['objective_delta']['schedule']='decay'
        with self.assertRaises(ValueError):c.validate_shape(changed, self.recipe)
        changed=copy.deepcopy(self.reg);del changed['objective_delta']
        with self.assertRaises(ValueError):c.validate_shape(changed, self.recipe)

    def test_existing_original_profile_stays_valid(self):
        c.validate_shape(self.prior, self.recipe)
        authority=c.read(self.root/'learning/runs/v2/fresh-control12-k1-m1-20261102-r2/authority.json')
        c.validate_authority(authority,self.prior)
        changed=copy.deepcopy(authority);changed['objective_delta']=self.reg['objective_delta']
        with self.assertRaises(ValueError):c.validate_authority(changed,self.prior)
        changed=copy.deepcopy(self.reg);changed['total_seconds']=7200
        with self.assertRaises(ValueError):c.validate_shape(changed, self.recipe)

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
            for key,value in [('source_run_id','other'),('seed_campaign','other')]:
                changed=copy.deepcopy(reg);changed['fresh_stream']['replay'][key]=value
                with self.assertRaises(ValueError):c.validate_training_replay(changed)
            changed=copy.deepcopy(reg);changed['input_pins'][ap]='0'*64
            with self.assertRaises(ValueError):c.validate_training_replay(changed)
            Path(rp).write_text(json.dumps(dict(accepted_audit_sha256=ah,lease_value_after_release={'held':True})))
            with self.assertRaises(ValueError):c.validate_training_replay(reg)

    def test_real_registered_stream_identity_and_authority_bindings(self):
        packet=self.root/'learning/runs/v2/control12-entropy001-m1-20261102-r1'
        self.reg=c.read(packet/'config.json')
        c.validate_authority(c.read(packet/'authority.json'),self.reg)
        replay=self.reg['fresh_stream']['replay']
        self.assertEqual(replay['source_run_id'],self.prior['run_id'])
        self.assertEqual(replay['seed_campaign'],self.prior['fresh_stream']['campaign'])
        self.assertNotIn('campaign_run_id',replay)
        local=self.root/'learning/runs/v2/fresh-control12-k1-m1-20261102-r2/inputs'
        files={'registry':'seed-registry-r1.json','history':'merged-conservative-seeds.json','pool':'training-pool512.json'}
        for key,name in files.items():
            binding=self.reg['fresh_stream'][key]
            path=local/name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),binding['sha256'])
            binding['path']=str(path)
        self.reg['fresh_stream']['stream_identity']='e6da144f37b0b13e69cbc1cf49b081bb70e2f33f5214b6801ec63b1cf09076e8'
        spec=specification(self.reg)
        self.assertIsInstance(spec,StreamSpec)
        self.assertEqual(spec.identity,'e6da144f37b0b13e69cbc1cf49b081bb70e2f33f5214b6801ec63b1cf09076e8')
        for campaign in [self.prior['run_id'],self.reg['run_id']]:
            changed=copy.deepcopy(self.reg);changed['fresh_stream']['campaign']=campaign
            with self.assertRaises(ValueError):specification(changed)
        # Mismatch each authority role independently against the real registration.
        auth=dict(training_execution_authorized=True,fresh_games_authorized=True,record=self.reg['record'],
            run_id=self.reg['run_id'],one_invocation=True,prepared_candidate_sha256=self.reg['prepared_candidate_sha256'],
            checkpoint_sha256=self.reg['warmstart']['sha256'],
            original_adam_fingerprint=self.reg['warmstart']['adam_fingerprint'],
            source_LR_unchanged=self.reg['ppo']['learning_rate'],
            seed_stream_identity=self.reg['fresh_stream']['stream_identity'],objective_delta=self.reg['objective_delta'])
        c.validate_authority(auth,self.reg)
        for key in ['record','run_id','prepared_candidate_sha256','checkpoint_sha256',
                    'original_adam_fingerprint','source_LR_unchanged','seed_stream_identity']:
            changed=dict(auth);changed[key]='wrong'
            with self.assertRaises(ValueError):c.validate_authority(changed,self.reg)
        changed=dict(auth);changed['one_invocation']=False
        with self.assertRaises(ValueError):c.validate_authority(changed,self.reg)
        changed=dict(auth);changed['objective_delta']=dict(parameter='ent_coef',before=.01,after=.002,schedule='constant')
        with self.assertRaises(ValueError):c.validate_authority(changed,self.reg)
        # Toy-domain lookup tests determinism only; registered data never calls seed_for.
        a=StreamSpec('toy-prior','one',2,'a'*64,bits=8)
        b=StreamSpec('toy-prior','one',2,'a'*64,bits=8)
        self.assertEqual([seed_for(a,0,i) for i in range(5)],[seed_for(b,0,i) for i in range(5)])


if __name__=='__main__':unittest.main()
