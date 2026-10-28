import unittest
from seed_priority import SCHEMA, validate_pool, sequence, inclusion_probabilities

class SeedPriorityTests(unittest.TestCase):
    def pool(self):
        rows=[]
        for i in range(512):
            rows.append({"seed":i+1,"stratum":"hard" if i<256 else "easy",
                         "training_evidence":{"role":"training","evaluation":False,
                                               "source_id":"synthetic-fixture"}})
        return {"schema":SCHEMA,"role":"training_only",
                "evaluation_seeds_used_for_selection":False,
                "history_closure":"parent_accepted_bounded_scope_no_universal_claim",
                "excluded_seed_ranges":[[0xD0000000,0xDFFFFFFF],[0xB0000000,0xBFFFFFFF]],
                "seeds":rows}

    def test_pool_requires_audited_training_only_balanced_input(self):
        info=validate_pool(self.pool())
        self.assertEqual(len(info["all"]),512)
        self.assertEqual(len(info["hard"]),256)
        invalid=self.pool(); invalid["seeds"][0]["training_evidence"]["evaluation"]=True
        with self.assertRaisesRegex(ValueError,"training-only"):
            validate_pool(invalid)

    def test_explicit_exposure_overlap_rejected(self):
        doc=self.pool(); doc["seeds"][0]["seed"]=0xD4000000
        with self.assertRaisesRegex(ValueError,"intersects"):
            validate_pool(doc)

    def test_priority_stream_deterministic_bounded_and_pool_only(self):
        pool=validate_pool(self.pool())
        a=sequence(pool,study_id="fixture",replica=1,env_master_seed=99,arm="opening_priority",slot=3,count=1000)
        b=sequence(pool,study_id="fixture",replica=1,env_master_seed=99,arm="opening_priority",slot=3,count=1000)
        self.assertEqual(a,b)
        self.assertTrue(set(a) <= set(pool["all"]))
        p=inclusion_probabilities(pool)
        self.assertEqual(p["uniform"],1/512)
        self.assertEqual(p["relative_cap"],1.5)
        self.assertLessEqual(p["relative_cap"],p["required_relative_cap"])

    def test_priority_arm_and_control_share_pool_but_sequence_domains_differ(self):
        pool=validate_pool(self.pool())
        uniform=sequence(pool,study_id="fixture",replica=1,env_master_seed=99,arm="uniform",slot=0,count=200)
        priority=sequence(pool,study_id="fixture",replica=1,env_master_seed=99,arm="opening_priority",slot=0,count=200)
        self.assertTrue(set(uniform) <= set(pool["all"]))
        self.assertTrue(set(priority) <= set(pool["all"]))
        self.assertNotEqual(uniform,priority)

if __name__ == "__main__": unittest.main()
