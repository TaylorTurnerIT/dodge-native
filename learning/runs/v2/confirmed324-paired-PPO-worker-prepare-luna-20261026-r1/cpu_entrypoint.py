"""CPU-only fake adapter entrypoint. No trained model, checkpoint, game, or env import."""
import json
from pathlib import Path
import worker
class FakeAPI:
 def __init__(self): self.events=[]; self.lrs=[]; self.journal=[]; self.saved=[]
 def event(self,x): self.events.append(x)
 def seed_initialization(self,s): self.events.append(("constructor_seed",s))
 def construct_model_adam(self): self.events.append("construct_model_adam"); return {},{"param_groups":[{"lr":3e-5}]}
 def fingerprints(self,m,o,r): return {"model":"3b72815fef4d8fa0084044739f5a5eaf9f74971b36dff9d8b26ed3bea5c562bc","Adam":"cf5e2a7ac5d3f7f131a26f7c2b8b778b7692850cff606a0ea9080941b960451c","RNG":"cb96ee8d2c40114a51abb8031dc7457a6da6d1be7262c6a4859bd34cab5813af"}
 def set_learning_rate(self,o,lr): o["param_groups"][0]["lr"]=lr; self.lrs.append(lr)
 def complete_ppo_update(self,m,o,e,**kw): return {"complete":True,"counter":kw["cumulative_update"]}
 def journal_update(self,*x): self.journal.append(x)
 def save_complete_candidate(self,*x): self.saved.append(x[:4])
 def finish_without_promotion(self,*a,**kw): self.events.append("finished_no_promotion")
class FakeCallbacks:
 def __init__(self): self.capture_count=0
 def capture_rng(self):
  self.capture_count+=1; return dict(python=1,numpy_global=2,numpy_generator=None,torch_cpu=3,torch_mps=4,sampling_backend="fake-cpu")
 def restore_trusted(self,m,o): pass
 def transition(self,**kw):
  return {"status":"transition_complete"}
def load_registration(path): return json.loads(Path(path).read_text())
def run(path):
 global REG,EVENTS
 REG=load_registration(path); EVENTS=[]; api=FakeAPI(); cb=FakeCallbacks(); made=[]
 def env_factory(**kw):
  EVENTS.append(("env",kw)); made.append(kw); return object()
 result=worker.prepare_run(REG,Path(__file__).resolve().parents[4],api,cb,object(),env_factory,Path("/tmp/fake-output"))
 return result,api,cb,EVENTS,made
