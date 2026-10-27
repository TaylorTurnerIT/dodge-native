import copy, json, unittest
from pathlib import Path
import worker
from cpu_entrypoint import FakeAPI, FakeCallbacks

ROOT=Path(__file__).resolve().parents[4]
DRAFT=Path(__file__).with_name('registration-draft.json')
class WorkerContracts(unittest.TestCase):
 def setUp(self):
  self.reg=json.loads(DRAFT.read_text())
  self.reg['arm']=worker.ARMS[1]; self.reg['replica']=1; self.reg['pair_id']='pair-1'
  v=self.reg['vectors']['1']; self.reg['vector_sha256']=v['vector_sha256']
  fixture=Path(__file__).with_name('fake-measured-reference-receipt.json'); fixture.write_text('{"fixture":"synthetic cpu test only"}\n')
  import hashlib
  self.reg['measured_references']={'receipt_path':str(fixture.resolve()),'receipt_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'status':'measured_accepted','parent_checkpoint_sha256':worker.PARENT['checkpoint_sha256'],'fields':sorted(worker.REFERENCE_FIELDS),'replicas':{'1':{k:'a'*64 for k in worker.REFERENCE_FIELDS}}}
  self.reg['status']='parent_review_required_not_launchable'
  self.reg['attempt_claim_path']='/tmp/never-created-claim'
 def test_pending_references_reject_before_any_api_event(self):
  api=FakeAPI(); self.reg['measured_references']['status']='pending_notrun'
  with self.assertRaisesRegex(ValueError,'measured RNG references'): worker.prepare_run(self.reg,ROOT,api,FakeCallbacks(),None,lambda **k:None,Path('/tmp/out'))
  self.assertEqual(api.events,[])
 def test_lr_and_counter_contract(self):
  self.assertEqual(worker.lr_for(worker.ARMS[0],373),3e-5)
  self.assertEqual(worker.lr_for(worker.ARMS[0],432),3e-5)
  self.assertEqual(worker.lr_for(worker.ARMS[1],373),3e-5)
  self.assertAlmostEqual(worker.lr_for(worker.ARMS[1],432),1e-5)
  self.assertAlmostEqual(worker.lr_for(worker.ARMS[1],402),3e-5+(1e-5-3e-5)*29/59)
  with self.assertRaises(ValueError): worker.lr_for(worker.ARMS[1],372)
 def test_end_to_end_fake_control_order_journal_and_exclusions(self):
  api=FakeAPI(); cb=FakeCallbacks(); events=[]; envs=[]
  def env_factory(**kw): events.append(('env',kw)); envs.append(kw); return object()
  class C(FakeCallbacks):
   def restore_trusted(self,*a): events.append('restore')
   def transition(self,**kw): events.append('transition_claim'); return {'status':'transition_complete'}
  result=worker.prepare_run(self.reg,ROOT,api,C(),None,env_factory,Path('/tmp/fake-output'))
  self.assertEqual(result['updates'],60); self.assertEqual(len(api.journal),60)
  self.assertEqual([x[2] for x in api.journal],[325+i for i in range(60)])
  self.assertEqual([x[1] for x in api.journal],[373+i for i in range(60)])
  self.assertEqual([x[2] for x in api.saved],[384,396,408,420,432])
  self.assertEqual(len(api.lrs),60); self.assertEqual(api.lrs[0],3e-5); self.assertAlmostEqual(api.lrs[-1],1e-5)
  self.assertEqual([e for e in events if isinstance(e,str)],['restore','transition_claim'])
  self.assertEqual(envs[0]['exclusions'],worker.EXCLUSIONS)
  self.assertEqual(envs[0]['initial_episode_indices'],self.reg['initial_episode_indices'])
  self.assertLess(events.index('transition_claim'),next(i for i,e in enumerate(events) if isinstance(e,tuple) and e[0]=='env'))
 def test_reference_key_mutation_and_registration_mutation_refuse(self):
  self.reg['vectors']['1']['seeds']['env_master_seed']+=1
  api=FakeAPI()
  with self.assertRaises(ValueError): worker.prepare_run(self.reg,ROOT,api,FakeCallbacks(),None,lambda **k:None,Path('/tmp/out'))
  self.assertEqual(api.events,[])

def main(): unittest.main()
if __name__=='__main__': main()
