"""Synthetic adapter callgraph test; imports no Torch, native module, or model."""
import importlib.util, sys, types, unittest
from pathlib import Path

PACKAGE=Path(__file__).resolve().parents[1]
RUNTIME=PACKAGE/"runtime/dodge_rl/seeded_training.py"

def episode(slot,index,seed,*,ended=False):
    return {"seed":{"slot":slot,"episode":index,"actual_seed":seed,"evaluation":True},
        "startup_frames":13,"alive_frames":0 if index else (0 if ended else 0),
        "gameplay_frames":0 if not ended else 4,"score_raw_fixed":0,
        "score_delta_sum_raw_fixed":0,"objective_return":-5.0 if ended else 0.0,
        "terminated":ended,"truncated":False,"bootstrap":not ended}

class FakeEnv:
    def __init__(self,streams):
        self.streams=streams
        self.current=[episode(0,0,streams[0][0]),episode(1,0,streams[1][0])]
    def batch_info(self):return {"batch_size":2,"seed_mode":{"mode":"evaluation","seeds_by_slot":self.streams}}
    def episode_info(self):return self.current

class SeededAdapterFakeTests(unittest.TestCase):
    def test_update_step_reset_and_terminal_binding(self):
        saved={k:sys.modules.get(k) for k in ("dodge_rl","dodge_rl.ppo","dodge_rl.seeded_training")}
        try:
            pkg=types.ModuleType("dodge_rl");pkg.__path__=[str(RUNTIME.parent)]
            ppo=types.ModuleType("dodge_rl.ppo");ppo._audit_episode=lambda *a,**kw:None
            sys.modules["dodge_rl"]=pkg;sys.modules["dodge_rl.ppo"]=ppo
            spec=importlib.util.spec_from_file_location("dodge_rl.seeded_training",RUNTIME)
            mod=importlib.util.module_from_spec(spec);sys.modules["dodge_rl.seeded_training"]=mod;spec.loader.exec_module(mod)
            streams=[[11,12],[21,22]];components=[["uniform","uniform"],["uniform","uniform"]]
            env=FakeEnv(streams);adapter=mod.SeededTrainingAdapter(env,seeds_by_slot=streams,
                components_by_slot=components,strata_by_seed={11:"hard",12:"easy",21:"easy",22:"hard"},
                training_pool_values=[11,12,21,22],exclusions=[])
            events=[];adapter.event_sink=events.append
            self.assertTrue(adapter.assignment_events[0]["seed"]["evaluation"])
            adapter.begin_update(1);adapter.before_step(env.current,0)
            done=episode(0,0,11,ended=True);ongoing=episode(1,0,21)
            result={"elapsed_raw_frames":[4,4],"info":[done,ongoing]}
            adapter.observe_returned_step(result);adapter.reconcile(result,env.current,0);adapter.record_step(result,env.current,0)
            adapter.before_reset([0],{0:done});reset=episode(0,1,12)
            adapter.observe_returned_reset([0],{"info":[reset]});adapter.record_reset([0],[reset],0)
            for decision in range(1,256):
                adapter.reconcile({"info":[reset,ongoing]},[reset,ongoing],decision)
            boundary=adapter._finish_after_ppo()
            self.assertEqual(boundary["completed_updates"],1)
            self.assertEqual(adapter.gameplay_frames,8)
            self.assertEqual(adapter.returned_resets[0]["indices"],[0])
            self.assertTrue(any(e["kind"]=="seeded_reset" for e in events))
            self.assertEqual(adapter.assignment_events[0]["sampling_component"],"uniform")
        finally:
            for name,value in saved.items():
                if value is None:sys.modules.pop(name,None)
                else:sys.modules[name]=value

if __name__=="__main__":unittest.main()
