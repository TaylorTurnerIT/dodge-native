import copy
import unittest

import numpy as np

import adapter

H = lambda c: c * 64


def result(checkpoint, cohort, backend, values, deaths=None):
    payload = {
        "checkpoint_sha256": checkpoint,
        "cohort_sha256": cohort,
        "backend": backend,
        "seeds": list(adapter.SEEDS),
        "alive_frames": list(map(float, values)),
        "death_counts": deaths or {"collision": int(len(values) - sum(v == adapter.RAW_FRAME_CAP for v in values))},
        "cap_count": int(sum(v == adapter.RAW_FRAME_CAP for v in values)),
    }
    return {**payload, "output_sha256": adapter.sha256_json(payload)}


def binding(value):
    return {"expected_output_sha256": value["output_sha256"], "result": value}


def fixture(wdiff=1.0):
    cohort = adapter.sha256_json(list(adapter.SEEDS))
    winner_hash, incumbent_hash = H("a"), adapter.EXPECTED_INCUMBENT_SHA256
    reg = {
        "status": "final_frozen",
        "confirmation": {"count": 2048, "first_seed": adapter.SEEDS[0], "last_seed": adapter.SEEDS[-1], "bootstrap_seed": 4200261026, "bootstrap_resamples": 20000, "quantile_method": "linear", "lower_percentile": 5.0, "statistic": "paired_mean_alive_frames_winner_minus_locked_incumbent", "eligible_rule": "LB>0"},
        "cohort_seeds": list(adapter.SEEDS), "cohort_sha256": cohort,
        "incumbent_checkpoint_sha256": incumbent_hash, "incumbent_phase_update": 348, "backend": "cpu-test",
    }
    sel = {"frozen": True, "phase_update": 324, "checkpoint_sha256": winner_hash}
    sel["selection_sha256"] = adapter.sha256_json(sel)
    audit = {"status": "successful", "terminal": True, "audit_id": "fixture"}
    audit["receipt_sha256"] = adapter.sha256_json(audit)
    inc = np.full(adapter.N, 100.0)
    win = inc + wdiff
    return reg, sel, audit, binding(result(winner_hash, cohort, "cpu-test", win)), binding(result(incumbent_hash, cohort, "cpu-test", inc))


class AdapterTests(unittest.TestCase):
    def run_fixture(self, diff):
        return adapter.analyze(*fixture(diff))

    def test_constant_positive_negative_zero(self):
        self.assertEqual(self.run_fixture(1)["eligibility"], "eligible")
        self.assertEqual(self.run_fixture(-1)["eligibility"], "inconclusive")
        self.assertEqual(self.run_fixture(0)["eligibility"], "inconclusive")

    def test_paired_resampling_differs_from_independent(self):
        args = list(fixture())
        common = np.tile([0.0, 100.0], adapter.N // 2)
        w = common + np.tile([2.0, 4.0], adapter.N // 2)
        i = common
        coh, wh, ih = args[0]["cohort_sha256"], args[1]["checkpoint_sha256"], args[0]["incumbent_checkpoint_sha256"]
        args[3] = binding(result(wh, coh, "cpu-test", w))
        args[4] = binding(result(ih, coh, "cpu-test", i))
        out = adapter.analyze(*args)
        self.assertEqual(out["finite_cohort_mean_difference_winner_minus_348"], 3.0)
        # Shared seed difficulty cancels in paired differences; independent draws do not cancel it.
        self.assertGreater(out["paired_bootstrap_lower_bound_5pct"], -10.0)
        self.assertEqual(out["bootstrap"]["same_seed_indices_for_both_models"], True)
        rng = np.random.Generator(np.random.PCG64(17))
        paired_means = np.empty(2000)
        independent_means = np.empty(2000)
        for start in range(0, 2000, 100):
            ix_w = rng.integers(0, adapter.N, size=(100, adapter.N))
            ix_i = rng.integers(0, adapter.N, size=(100, adapter.N))
            paired_means[start:start + 100] = (w - i)[ix_w].mean(axis=1)
            independent_means[start:start + 100] = w[ix_w].mean(axis=1) - i[ix_i].mean(axis=1)
        self.assertLess(paired_means.std(), independent_means.std())

    def test_rejects_reordered_missing_duplicate(self):
        for mutate in (lambda s: s.reverse(), lambda s: s.pop(), lambda s: s.__setitem__(1, s[0])):
            args = fixture()
            args[3]["result"]["seeds"] = list(args[3]["result"]["seeds"])
            mutate(args[3]["result"]["seeds"])
            payload = {k: v for k, v in args[3]["result"].items() if k != "output_sha256"}
            args[3]["result"]["output_sha256"] = adapter.sha256_json(payload)
            args[3]["expected_output_sha256"] = args[3]["result"]["output_sha256"]
            with self.assertRaises(adapter.ContractError):
                adapter.analyze(*args)

    def test_repeat_determinism_and_quantile_linear_boundary(self):
        one = self.run_fixture(0.25)
        two = self.run_fixture(0.25)
        self.assertEqual(one, two)
        np.testing.assert_equal(np.quantile([0.0, 10.0], 0.05, method="linear"), 0.5)
        self.assertEqual(one["paired_bootstrap_lower_bound_5pct"], 0.25)

    def test_caps_included_and_full_counts(self):
        args = list(fixture(0))
        args[3] = binding(result(args[1]["checkpoint_sha256"], args[0]["cohort_sha256"], "cpu-test", [18000.0] + [100.0] * (adapter.N - 1), {"collision": adapter.N - 1}))
        args[4] = binding(result(args[0]["incumbent_checkpoint_sha256"], args[0]["cohort_sha256"], "cpu-test", [18000.0] + [100.0] * (adapter.N - 1), {"collision": adapter.N - 1}))
        out = adapter.analyze(*args)
        self.assertEqual(out["winner"]["cap_count"], 1)
        self.assertEqual(out["winner"]["death_counts"], {"collision": adapter.N - 1})
        self.assertEqual(out["finite_cohort_mean_difference_winner_minus_348"], 0.0)

    def test_tamper_and_failed_audit_rejected(self):
        args = fixture()
        args[3]["result"]["alive_frames"][0] += 1
        with self.assertRaisesRegex(adapter.ContractError, "tampered"):
            adapter.analyze(*args)
        args = fixture()
        args[3]["result"]["alive_frames"][0] += 1
        args[3]["result"]["output_sha256"] = adapter.sha256_json({k: v for k, v in args[3]["result"].items() if k != "output_sha256"})
        with self.assertRaisesRegex(adapter.ContractError, "external pinned"):
            adapter.analyze(*args)
        args = fixture()
        args[2]["status"] = "failed"
        args[2]["receipt_sha256"] = adapter.sha256_json({k: v for k, v in args[2].items() if k != "receipt_sha256"})
        with self.assertRaisesRegex(adapter.ContractError, "failed"):
            adapter.analyze(*args)

    def test_invalid_alive_backend_and_cohort_rejected(self):
        for change in ("nan", "cap", "backend", "cohort"):
            args = fixture()
            if change == "nan":
                args[3]["result"]["alive_frames"][4] = float("nan")
            elif change == "cap":
                args[3]["result"]["alive_frames"][4] = 18001.0
            elif change == "backend":
                args[3]["result"]["backend"] = "other"
            else:
                args[3]["result"]["cohort_sha256"] = H("c")
            if change != "nan":
                payload = {k: v for k, v in args[3].items() if k != "output_sha256"}
                args[3]["output_sha256"] = adapter.sha256_json(payload)
            with self.assertRaises(adapter.ContractError):
                adapter.analyze(*args)


if __name__ == "__main__":
    unittest.main()
