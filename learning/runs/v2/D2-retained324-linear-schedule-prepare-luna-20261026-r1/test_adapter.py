import unittest
import torch
import adapter_draft as a

class AdapterContractTests(unittest.TestCase):
 def setUp(self):
  torch.set_num_threads(1)
  self.opt=torch.optim.Adam([torch.nn.Parameter(torch.tensor([1.]))],lr=3e-5)
 def test_origin_and_independent_counters(self):
  st=a.initialize_at_verified_origin(self.opt,{'updates':372},{'updates':0})
  self.assertEqual(a.actual_cumulative_updates({'updates':372},{'updates':0}),372)
  with self.assertRaisesRegex(ValueError,'inherited updates'):
   a.actual_cumulative_updates({'updates':371},{'updates':1})
  with self.assertRaisesRegex(ValueError,'only at verified origin'):
   a.initialize_at_verified_origin(self.opt,{'updates':372},{'updates':1})
  lr, staged=a.stage_before_ppo(self.opt,st,{'updates':372},{'updates':0})
  self.assertEqual(lr,3e-5); self.assertEqual(staged['completed_schedule_updates'],1)
  self.assertEqual(st['completed_schedule_updates'],0) # failure path leaves metadata uncommitted
 def test_restore_missing_metadata_hard_fails(self):
  with self.assertRaisesRegex(ValueError,'missing lr_schedule'):
   a.restore_schedule_state({},self.opt)
 def test_entry_lr_and_scheduled_saved_lr(self):
  st=a.initialize_at_verified_origin(self.opt,{'updates':372},{'updates':0})
  self.assertEqual(a.expected_saved_lr(st,372),3e-5)
  for n in range(60):
   _,st=a.stage_before_ppo(self.opt,st,{'updates':372},{'updates':n})
  self.assertEqual(a.expected_saved_lr(st,432),1e-5)
  self.assertEqual(a.expected_saved_lr(st,500),1e-5)
 def test_progress_mismatch_rejected(self):
  st=a.initialize_at_verified_origin(self.opt,{'updates':372},{'updates':0})
  with self.assertRaisesRegex(ValueError,'do not match actual'):
   a.stage_before_ppo(self.opt,st,{'updates':372},{'updates':1})

if __name__=='__main__': unittest.main()
