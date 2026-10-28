"""CPU-only TinyNet integration for the explicit-seed collector contract."""
import sys
import json
import tempfile
import unittest
from pathlib import Path

import torch

PACKAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PACKAGE/"tests"))
from fakes import FakeEnv, TinyNet
from successor import ppo
from successor.curriculum import PreparedUpdates
from successor.seeded_training import SeededTrainingAdapter
sys.path.insert(0,str(PACKAGE))
from terminal import accounting


class ExplicitSeedEnv(FakeEnv):
    def __init__(self):
        super().__init__(64)
        self.streams=[[100+slot,164+slot] for slot in range(64)]
        for row in self.infos:
            row["seed"]["evaluation"]=True

    def batch_info(self):
        value=super().batch_info()
        value["seed_mode"]={"mode":"evaluation","seeds_by_slot":self.streams}
        return value

    def step(self,actions):
        result=super().step(actions)
        for row in result["info"]:row["seed"]["evaluation"]=True
        for row in self.infos:row["seed"]["evaluation"]=True
        return result

    def reset_done(self,indices):
        result=super().reset_done(indices)
        for row in result["info"]:row["seed"]["evaluation"]=True
        for slot in indices:self.infos[slot]["seed"]["evaluation"]=True
        return result


class SeededPipelineCpuFakeTests(unittest.TestCase):
    def test_collector_and_prepared_update_preserve_explicit_seed_costs(self):
        env=ExplicitSeedEnv()
        seeds=[seed for stream in env.streams for seed in stream]
        strata={seed:("hard" if seed%2 else "easy") for seed in seeds}
        adapter=SeededTrainingAdapter(env,seeds_by_slot=env.streams,
            components_by_slot=[["uniform","uniform"] for _ in range(64)],
            strata_by_seed=strata,training_pool_values=seeds,exclusions=[])
        events=[];adapter.event_sink=events.append
        model=TinyNet()
        optimizer=torch.optim.Adam(model.parameters(),lr=3e-5,eps=1e-5)
        prepared=PreparedUpdates(model,optimizer,adapter,config=ppo.PPOConfig(learning_rate=3e-5))
        collection,metrics,boundary=prepared.update_once()
        decisions=collection.batch.actions.numel()
        raw_frames=int(collection.batch.elapsed_raw_frames.sum().item())
        self.assertEqual(decisions,64*256)
        self.assertEqual(raw_frames,64*256*4)
        self.assertEqual(adapter.observed_native_frames,raw_frames)
        self.assertEqual(adapter.gameplay_frames,raw_frames)
        self.assertEqual(boundary["completed_updates"],1)
        self.assertEqual(metrics["optimizer_steps"],prepared.actual_optimizer_steps)
        self.assertEqual(adapter.initial_startup_frames,13*64)
        self.assertEqual(adapter.returned_reset_startup_frames,0)
        self.assertEqual(adapter.assignment_events[0]["sampling_component"],"uniform")
        self.assertEqual(len(events),2*256)
        self.assertEqual(sum(event["kind"]=="returned_step_cost" for event in events),256)
        self.assertEqual(sum(event["kind"]=="seeded_step" for event in events),256)

    def test_terminal_age_bins_and_raw_cost_conservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pool_path=root/"pool.json";out=root/"out";out.mkdir()
            rows=[{"seed":seed,"stratum":"hard" if seed<257 else "easy",
                "training_evidence":{"evaluation":False,"role":"training"}}
                for seed in range(1,513)]
            pool={"schema":"dodge_seed_priority_pool_v1","role":"training_only",
                "evaluation_seeds_used_for_selection":False,
                "history_closure":"parent_accepted_bounded_scope_no_universal_claim",
                "excluded_seed_ranges":[[1000,1100]],"seeds":rows}
            pool_path.write_text(json.dumps(pool))
            assignments=[];completed=[]
            for slot,seed in enumerate(range(1,65)):
                stratum=rows[seed-1]["stratum"]
                seed_doc={"slot":slot,"episode":0,"actual_seed":seed,"evaluation":True}
                assignments.append({"slot":slot,"seed":seed_doc,"sampling_component":"uniform","stratum":stratum})
                completed.append({"seed":seed_doc,"gameplay_frames":4,"sampling_component":"uniform","stratum":stratum})
            events=[{"kind":"initial","assignments":assignments},
                {"kind":"returned_step_cost","elapsed_raw_frames":[4]*64},
                {"kind":"collection_complete_before_PPO","completed":completed}]
            (out/"training-events.jsonl").write_text("".join(json.dumps(row)+"\n" for row in events))
            adapter={"initial_startup_frames":13*64,"reset_startup_frames":0,
                "returned_reset_startup_frames":0,"reset_count":0,
                "observed_native_frames":64*4,"gameplay_frames":64*4}
            data=accounting(out,{"registration":{"training_pool_path":str(pool_path)},
                "final_snapshot":{"environment":adapter,"current_episode_info":[]}},strict=True)
            self.assertEqual(data["returned_native_raw_frames"],256)
            self.assertEqual(data["age_binned_gameplay_frame_total"],256)
            self.assertEqual(data["assignment_component_counts"]["uniform"],64)


if __name__=="__main__":unittest.main()
