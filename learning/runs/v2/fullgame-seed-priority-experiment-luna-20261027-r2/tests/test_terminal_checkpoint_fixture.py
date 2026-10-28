"""Stdlib terminal fixture built from the real successor learner identity producer."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from successor_identity import learner_identity
from terminal import validate_outputs


class TerminalCheckpointFixtureTests(unittest.TestCase):
    def test_terminal_accepts_real_nested_identity_and_checkpoint_receipt_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/"output";out.mkdir()
            pool_path=root/"pool.json"
            pool_rows=[{"seed":seed,"stratum":"hard" if seed<=256 else "easy",
                "training_evidence":{"evaluation":False,"role":"training"}}
                for seed in range(1,513)]
            pool={"schema":"dodge_seed_priority_pool_v1","role":"training_only",
                "evaluation_seeds_used_for_selection":False,
                "history_closure":"parent_accepted_bounded_scope_no_universal_claim",
                "excluded_seed_ranges":[[1000,1100]],"seeds":pool_rows}
            pool_path.write_text(json.dumps(pool))
            seeds=[{"slot":slot,"episode":0,"actual_seed":slot+1,"evaluation":True}
                for slot in range(64)]
            assignments=[{"slot":slot,"seed":seeds[slot],"sampling_component":"uniform",
                "stratum":pool_rows[slot]["stratum"]} for slot in range(64)]
            events=[{"kind":"initial","assignments":assignments}]
            events.extend({"kind":"returned_step_cost","elapsed_raw_frames":[0]*64}
                for _ in range(60*256))
            (out/"training-events.jsonl").write_text("".join(json.dumps(row)+"\n" for row in events))

            reg={"run_id":"fixture-run","pair_id":"fixture-pair","replica":1,"arm":"uniform",
                "backend":"mps","training_pool_path":str(pool_path),"training_pool_sha256":"pool-semantic-sha",
                "source_manifest_sha256":"1"*64,"runtime_manifest_sha256":"2"*64,
                "runtime_versions":{"python":"3.12"},"shared_config":{"fixture":True},
                "vector":{"seeds":{"env_master_seed":1}},"slot_stream_sha256":["3"*64]*64,
                "schedule":{"updates":60},"exclusion_union":[[1000,1100]],
                "parent_checkpoint_sha256":"4"*64,"output":str(out)}
            registration_sha="5"*64
            identity=learner_identity(reg,registration_sha)
            checkpoint=out/"checkpoint-global-060-integrity.pt"
            checkpoint.write_bytes(b"synthetic checkpoint bytes; never a model")
            checkpoint_sha=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
            identity_sha=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(",",":"),
                allow_nan=False).encode()).hexdigest()
            checkpoint_receipt={"path":str(checkpoint),"sha256":checkpoint_sha,"global_update":60,
                "phase_update":384,"cumulative_update":432,"formal_comparison_endpoint":True,
                "identity":identity,"identity_sha256":identity_sha,
                "parent_checkpoint_sha256":reg["parent_checkpoint_sha256"]}
            Path(str(checkpoint)+".json").write_text(json.dumps(checkpoint_receipt))
            metrics=[]
            for update in range(1,61):
                metrics.append({"global_update":update,"counters":{"updates":update,
                    "optimizer_steps":update,"environment_decisions":update*16384,"raw_frames":0}})
            (out/"training-metrics.jsonl").write_text("".join(json.dumps(row)+"\n" for row in metrics))
            current=[{"seed":seed,"gameplay_frames":0} for seed in seeds]
            worker={"run_id":reg["run_id"],"registration_sha256":registration_sha,"status":"completed",
                "updates":60,"training_eligible":False,"promoted":False,"automatic_selection":False,
                "counters":{"updates":60,"optimizer_steps":60,"environment_decisions":983040,"raw_frames":0},
                "final_snapshot":{"environment":{"initial_startup_frames":13*64,
                    "returned_reset_startup_frames":0,"reset_startup_frames":0,"reset_count":0,
                    "observed_native_frames":0,"gameplay_frames":0},"current_episode_info":current},
                "integrity_checkpoints":[checkpoint_receipt]}
            result=validate_outputs(reg,worker,registration_sha)
            self.assertEqual(result["terminal_update"],60)
            self.assertEqual(result["accounting"]["age_binned_gameplay_frame_total"],0)
            self.assertEqual(identity["successor_runtime"]["source_manifest_sha256"],reg["source_manifest_sha256"])


if __name__=="__main__":unittest.main()
