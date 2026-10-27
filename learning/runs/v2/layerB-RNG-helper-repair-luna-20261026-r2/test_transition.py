"""Stdlib-only fake API tests; never imports torch, NumPy, native, or checkpoints."""
import ast, hashlib, json, re, unittest
from pathlib import Path
from types import SimpleNamespace
import transition as t
ROOT=Path(__file__).resolve().parents[4]
META=json.loads((Path(__file__).parent/'seed-vectors-successor-metadata.json').read_text())
PINNED=(ROOT/'learning/.venv/lib/python3.12/site-packages/torch/mps/__init__.py').read_text()
VECTORS=[v['seeds'] for v in META['vectors']]
RANGES=json.loads((ROOT/'learning/runs/v2/expanded-eval-parent-integration-20261026-r1/prospective-training-exclusions.json').read_text())['excluded_seed_ranges']
CONTROLS=META['vectors'][0]['env_control']['episode_controls']

def mps_functions():
    tree=ast.parse(PINNED)
    return {n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}

class FakeMPS:
    def __init__(self,events): self.seed_value=None; self.events=events
    def manual_seed(self,seed): self.events.append('mps'); self.seed_value=seed
    def get_rng_state(self): return f'mps:{self.seed_value}'.encode()
class FakeTorch:
    def __init__(self,available=True,reverse=False,bad_state=False):
        self.events=[]; self.backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda:available)); self.mps=FakeMPS(self.events); self.cpu=None; self.reverse=reverse; self.bad_state=bad_state
    def manual_seed(self,seed): self.events.append('cpu'); self.cpu=seed; self.mps.seed_value=seed
    def initial_seed(self): return self.cpu
    def get_rng_state(self): return b'bad' if self.bad_state else f'cpu:{self.cpu}'.encode()
class FakeOpt:
    def __init__(self): self.param_groups=[{'lr':9e-5,'weight_decay':0.2,'betas':(0.8,0.9)}]; self.state={'p':{'step':7,'exp_avg':[1,2],'exp_avg_sq':[3,4]}}
class FakeSeeder:
    def __init__(self): self.value=None
    def seed(self,v): self.value=v

def fingerprint(b): return hashlib.sha256(b).hexdigest()
def expected(seeds):
    return {'torch_cpu_global_seed':fingerprint(f"cpu:{seeds['torch_cpu_global_seed']}".encode()),'action_sampler_torch_mps_seed':fingerprint(f"mps:{seeds['action_sampler_torch_mps_seed']}".encode())}

def make_call(seeds=None, *, available=True, bad_state=False, source=None):
    seeds=dict(seeds or VECTORS[0]); pair={'pair_id':'p','A':dict(seeds),'B':dict(seeds)}; calls=[]
    torch=FakeTorch(available,bad_state=bad_state); opt=FakeOpt(); session=t.TransitionSession(); live={'model':'fresh-model','Adam':'fresh-adam','RNG':'fresh-rng'}
    def restore(): calls.append('restore'); live.update(t.EXPECTED_PARENT)
    def current(): return dict(live)
    def verify(): calls.append('verify'); return dict(source or {'receipt_sha256':t.ACCEPTED_PARENT_RECEIPT_SHA256,'checkpoint_fingerprints':t.EXPECTED_PARENT})
    kw=dict(session=session,backend='mps',seeds=seeds,pair=pair,verify_trusted_source=verify,restore_trusted=restore,current_fingerprints=current,expected_state_digests=expected(seeds),state_fingerprint=fingerprint,python_api=FakeSeeder(),numpy_api=FakeSeeder(),torch_api=torch,optimizer=opt,pair_id='p',arm='B_linear_3e-5_to_1e-5_over_60')
    return kw,calls,torch,opt,live

class Tests(unittest.TestCase):
    def test_fake_surface_has_only_pinned_mps_methods(self):
        self.assertTrue({'manual_seed','get_rng_state'} <= mps_functions())
        self.assertFalse(hasattr(FakeMPS([]),'initial_seed'))
    def test_fresh_live_state_restores_and_seed_order(self):
        kw,calls,torch,opt,live=make_call(); out=t.transition(**kw)
        self.assertEqual(calls,['verify','restore']); self.assertEqual(torch.mps.seed_value,kw['seeds']['action_sampler_torch_mps_seed']); self.assertEqual(torch.events,['cpu','mps'])
        self.assertEqual(out['seed_evidence']['torch_cpu_initial_seed'],kw['seeds']['torch_cpu_global_seed'])
        self.assertEqual(opt.param_groups[0]['lr'],3e-5)
    def test_source_mismatch_before_restore_or_mutation(self):
        kw,calls,_,opt,_=make_call(source={'receipt_sha256':'bad','checkpoint_fingerprints':t.EXPECTED_PARENT})
        with self.assertRaisesRegex(ValueError,'source'): t.transition(**kw)
        self.assertEqual(calls,['verify']); self.assertEqual(opt.param_groups[0]['lr'],9e-5)
    def test_bad_state_and_reverse_order_detected_after_restore(self):
        kw,calls,torch,_,_=make_call(bad_state=True)
        with self.assertRaisesRegex(ValueError,'CPU state digest'): t.transition(**kw)
        self.assertEqual(calls,['verify','restore'])
        # Deliberately replace CPU seed method with reversed implementation.
        kw,calls,torch,_,_=make_call(); torch.events=[]
        torch.manual_seed=lambda seed: (torch.events.append('mps'), setattr(torch,'cpu',seed), setattr(torch.mps,'seed_value',seed))
        original=torch.mps.manual_seed
        torch.mps.manual_seed=lambda seed: (torch.events.append('mps'), setattr(torch.mps,'seed_value',seed+1))
        with self.assertRaisesRegex(ValueError,'MPS state digest'): t.transition(**kw)
    def test_unavailable_mps_before_mutation(self):
        kw,calls,_,opt,_=make_call(available=False)
        with self.assertRaisesRegex(ValueError,'unavailable'): t.transition(**kw)
        self.assertEqual(calls,[]); self.assertEqual(opt.param_groups[0]['lr'],9e-5)
    def test_second_invocation_and_mutable_failure_consume_session(self):
        kw,_,_,_,_=make_call(); t.transition(**kw)
        with self.assertRaisesRegex(RuntimeError,'no retry'): t.transition(**kw)
        kw,_,_,_,_=make_call(bad_state=True)
        with self.assertRaises(ValueError): t.transition(**kw)
        with self.assertRaisesRegex(RuntimeError,'no retry'): t.transition(**kw)
    def test_optimizer_state_and_group_fields_preserved(self):
        kw,_,_,opt,_=make_call(); state=json.dumps(opt.state,sort_keys=True); group=dict(opt.param_groups[0]); t.transition(**kw)
        self.assertEqual(opt.state,json.loads(state)); self.assertEqual({k:v for k,v in opt.param_groups[0].items() if k!='lr'},{k:v for k,v in group.items() if k!='lr'})
    def test_sorted_proposal_ranges_and_all_three_vectors(self):
        for seeds in VECTORS:
            controls=[]
            for row in CONTROLS:
                controls.append({**row})
            t.validate_exclusion_controls(RANGES,controls)
            self.assertEqual(len(seeds),6)
    def test_range_shape_bounds_overlap_duplicates_and_controls_reject(self):
        for ranges in (RANGES[:-1], RANGES+[RANGES[0]], [[-1,4]]+RANGES[1:], [[1,5],[5,7]]+RANGES[2:]):
            with self.subTest(ranges=ranges), self.assertRaises(ValueError): t.validate_exclusion_controls(ranges,CONTROLS)
        for mutate in ('missing','wrong','collision','counter'):
            rows=[dict(r) for r in CONTROLS]
            if mutate=='missing': rows.pop()
            if mutate=='wrong': rows[0]['slot']=rows[1]['slot']
            if mutate=='collision': rows[0]['first_actual_seed']=RANGES[0][0]
            if mutate=='counter': rows[0]['rejection_counter']=-1
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): t.validate_exclusion_controls(RANGES,rows)
    def test_pair_mismatch_endpoints_prior_master_and_cpu_fingerprint(self):
        pair={'pair_id':'p','A':dict(VECTORS[0]),'B':dict(VECTORS[1])}
        with self.assertRaisesRegex(ValueError,'identical'): t.validate_pair(pair)
        self.assertEqual(t.controller_lr('B_linear_3e-5_to_1e-5_over_60',397),3e-5)
        self.assertEqual(t.controller_lr('B_linear_3e-5_to_1e-5_over_60',456),1e-5)
        bad=dict(VECTORS[0],env_master_seed=5562881586070242562)
        with self.assertRaisesRegex(ValueError,'prior master'): t.validate_seeds(bad)
        kw,_,_,_,_=make_call(); kw['expected_state_digests']['torch_cpu_global_seed']='0'*64
        with self.assertRaisesRegex(ValueError,'CPU state digest'): t.transition(**kw)

if __name__=='__main__': unittest.main(verbosity=2)
