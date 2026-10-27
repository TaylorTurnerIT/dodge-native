"""PPO episode-boundary mathematics, budgets, RNG ownership, and native smoke."""

from __future__ import annotations

import importlib.util
import io
import json
import random
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import asdict, replace
from fractions import Fraction
from pathlib import Path
from unittest import mock

HAS_MODELS = (
    importlib.util.find_spec("torch") is not None
    and importlib.util.find_spec("numpy") is not None
)
HAS_NATIVE = importlib.util.find_spec("dodge_learning._native") is not None
if HAS_MODELS:
    import numpy as np
    import torch

    from dodge_learning.ppo import PPOConfig, compute_gae, train_teacher
    from dodge_learning import ppo
    from dodge_learning.entity_teacher import EntityActorCritic, EntityTeacherConfig, encode_entities
    from dodge_learning.teacher import StateActorCritic, TeacherConfig


class FakeEnvironment:
    instances = []

    def __init__(self, *, seed, max_episode_frames, action_repeat, discount):
        self.max_frames = max_episode_frames
        self.resets = []
        self.actions = []
        self.closed = False
        self.seed = seed
        self.frames = 0
        self.discount = discount
        if action_repeat != 1:
            raise AssertionError("teacher must use repeat 1")
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def reset(self, seed):
        self.seed = seed
        self.frames = 0
        self.resets.append(seed)
        return self.observation()

    def observation(self):
        terminated = self.seed == 1_001 and self.frames >= 2
        truncated = not terminated and self.frames >= self.max_frames
        return {
            "privileged_state": {
                "schema_version": 1,
                "globals": [0.0] * 64,
                "entities": [{"features": [(64.0 + self.frames) / 128, .5, 0., 0., .5] + [0.] * 27,
                              "kind": 0, "bounds": [64., 64., 68., 68.], "spatial": False}],
                "capture_bounds": [0., 0., 128., 128.],
            },
            "train_only_state": {
                "player": {"x": 64.0 + self.frames, "y": 64.0, "vx": 0.0, "vy": 0.0, "size": 4.0},
                "globals": {"speed": 1.0, "freeze_rate": 1.0, "freeze_active": False},
                "enemies": [], "rectangles": [], "warnings": [],
            },
            "reward_sum": 0.0 if terminated or self.frames == 0 else 1.0,
            "info": {
                "episode_frames": self.frames,
                "elapsed_native_frames": int(self.frames > 0),
                "terminated": terminated, "truncated": truncated,
                "pattern_completions": 0,
                "provenance": {"feature_schema_version": 2, "privileged_schema_version": 1, "core_schema_version": 1},
            },
        }

    def step(self, action):
        previous = self.observation()["info"]
        if previous["terminated"] or previous["truncated"]:
            raise AssertionError("trainer stepped a finished episode")
        self.actions.append(action)
        self.frames += 1
        return self.observation()


@unittest.skipUnless(HAS_MODELS, "install the optional PyTorch model extra")
class GAETests(unittest.TestCase):
    def test_truncation_bootstraps_final_observation_and_cuts_the_next_episode_trace(self):
        advantages, returns = compute_gae(
            [1, 2, 3], [.5, .7, .9], [.7, 5, 999],
            [False, False, True], [False, True, False], gamma=.9, gae_lambda=.8,
        )
        np.testing.assert_allclose(advantages, [5.306, 5.8, 2.1], rtol=1e-6)
        np.testing.assert_allclose(returns, [5.806, 6.5, 3], rtol=1e-6)
        self.assertEqual(advantages.dtype, np.float32)

    def test_rollout_end_bootstraps_while_death_does_not(self):
        _, continued = compute_gae([1], [.5], [2], [False], [False], gamma=.9, gae_lambda=.95)
        _, truncated = compute_gae([1], [.5], [2], [False], [True], gamma=.9, gae_lambda=.95)
        _, terminal = compute_gae([1], [.5], [999], [True], [False], gamma=.9, gae_lambda=.95)
        np.testing.assert_allclose(continued, [2.8])
        np.testing.assert_array_equal(continued, truncated)
        np.testing.assert_array_equal(terminal, [1])

    def test_gae_rejects_nonfinite_mismatched_or_conflicting_inputs(self):
        for args in (
            ([1], [0, 1], [0], [False], [False]),
            ([[1]], [[0]], [[0]], [[False]], [[False]]),
            ([float("nan")], [0], [0], [False], [False]),
            ([1], [0], [0], [True], [True]),
            ([1], [0], [0], [.5], [False]),
            ([1], [0], [0], [0], [False]),
            ([1], [0], [0], [False], [1.0]),
            ([1e300], [0], [0], [False], [False]),
            ([10**1000], [0], [0], [False], [False]),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                compute_gae(*args, gamma=.99, gae_lambda=.95)


@unittest.skipUnless(HAS_MODELS, "install the optional PyTorch model extra")
class PPOTrainingTests(unittest.TestCase):
    def setUp(self):
        FakeEnvironment.instances = []

    def config(self, **changes):
        config = PPOConfig(
            total_frames=7, max_seconds=30, rollout_steps=4, epochs=1, minibatch_size=4,
            max_episode_frames=3, train_seeds=(1_000, 1_001),
        )
        return replace(config, **changes)

    def test_hyperparameter_and_manifest_validation(self):
        invalid = (
            {"total_frames": 0}, {"total_frames": 100_001}, {"total_frames": True},
            {"rollout_steps": 4_097}, {"epochs": 0}, {"epochs": 17},
            {"minibatch_size": 0}, {"max_seconds": 0}, {"max_seconds": 1_801},
            {"max_seconds": float("nan")}, {"gamma": 0}, {"gamma": 1.1},
            {"gae_lambda": -1}, {"gae_lambda": float("inf")},
            {"learning_rate": 0}, {"clip_ratio": 0}, {"max_grad_norm": 0},
            {"reward_scale": 0}, {"reward_scale": -0.1}, {"reward_scale": 1.1},
            {"reward_scale": True}, {"reward_scale": float("nan")},
            {"entropy_coef": -1}, {"value_coef": float("nan")},
            {"critic_trunk_grad": 0}, {"critic_trunk_grad": 1},
            {"critic_trunk_grad": None}, {"critic_trunk_grad": "false"},
            {"critic_trunk_grad": np.bool_(False)},
            {"torch_threads": True}, {"torch_threads": 0},
            {"max_episode_frames": 18_001}, {"train_seeds": ()},
            {"train_seeds": (0, 1)}, {"train_seeds": (1, 1)},
            {"train_seeds": (-1,)}, {"train_seeds": (True,)},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                PPOConfig(**changes)
        for name in (
            "max_seconds", "learning_rate", "gamma", "gae_lambda", "clip_ratio",
            "value_coef", "entropy_coef", "max_grad_norm",
            "reward_scale",
        ):
            for value in (10**1000, Fraction(10**1000, 3)):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    PPOConfig(**{name: value})
        config = PPOConfig(train_seeds=[100, 101])
        self.assertEqual(config.train_seeds, (100, 101))
        json.dumps(asdict(config), allow_nan=False)

    def test_exact_frame_budget_partial_rollout_and_explicit_seed_resets(self):
        progress = []
        result = train_teacher(self.config(), environment_factory=FakeEnvironment,
                               progress_callback=progress.append)
        metrics = result.metrics
        self.assertEqual(metrics["frames_collected"], 7)
        self.assertEqual(metrics["updates"], 2)
        self.assertEqual(metrics["last_rollout_frames"], 3)
        self.assertEqual(metrics["optimizer_steps"], 2)
        self.assertEqual(metrics["samples_optimized"], 7)
        self.assertEqual(metrics["unoptimized_frames"], 0)
        self.assertEqual(metrics["episodes_completed"], 2)
        self.assertEqual(metrics["terminal_episodes"], 1)
        self.assertEqual(metrics["truncated_episodes"], 1)
        self.assertEqual(metrics["partial_episode_frames"], 2)
        self.assertEqual(FakeEnvironment.instances[0].resets, [1_000, 1_001, 1_000])
        self.assertTrue(FakeEnvironment.instances[0].closed)
        self.assertEqual([entry["frames_collected"] for entry in progress], [4, 7])
        self.assertEqual(metrics["stop_reason"], "frame_budget")
        self.assertTrue(result.optimizer_state["state"])
        json.dumps(metrics, allow_nan=False)

    def test_reward_scale_changes_gae_targets_without_changing_raw_episode_returns(self):
        with mock.patch("dodge_learning.ppo.compute_gae", wraps=compute_gae) as gae:
            result = train_teacher(self.config(reward_scale=.25), environment_factory=FakeEnvironment)
        self.assertEqual([call.args[0] for call in gae.call_args_list], [[.25] * 4, [0., .25, .25]])
        self.assertEqual(result.metrics["episode_return_mean"], 2.)
        self.assertEqual(result.metrics["partial_episode_return"], 2.)
        self.assertEqual(result.metrics["reward_scale"], .25)
        self.assertEqual(result.metrics["episode_return_units"], "native_survival_frames")

    def test_rollout_reuses_encoded_states_and_outputs_but_invalidates_after_updates_and_resets(self):
        forward_calls = []
        original_forward = ppo._forward

        def traced_forward(model, states):
            if not torch.is_grad_enabled():
                forward_calls.append((
                    round(float(states[0].features[0, 0]) * 128),
                    tuple(parameter._version for parameter in model.parameters()),
                ))
            return original_forward(model, states)

        with (
            mock.patch("dodge_learning.ppo._forward", side_effect=traced_forward),
            mock.patch("dodge_learning.ppo._encoded_observation", wraps=ppo._encoded_observation) as encode,
        ):
            result = train_teacher(self.config(), environment_factory=FakeEnvironment)
        # Seven transitions plus the first observation of each of three
        # episodes are encoded once. The death observation is still validated.
        self.assertEqual(encode.call_count, 10)
        self.assertEqual([x for x, _ in forward_calls], [64, 65, 66, 67, 64, 65, 65, 64, 65, 66])
        # The repeated frame-1 value belongs to different PPO parameter sets:
        # the first window's cached bootstrap cannot become a stale action.
        self.assertNotEqual(forward_calls[5][1], forward_calls[6][1])
        self.assertEqual(result.metrics["optimizer_steps"], 2)

    def test_rollout_does_not_reuse_stochastic_dropout_outputs(self):
        no_grad_calls = []
        original_forward = ppo._forward

        def traced_forward(model, states):
            no_grad_calls.append(not torch.is_grad_enabled())
            return original_forward(model, states)

        with torch.random.fork_rng(devices=[]):
            model = EntityActorCritic(EntityTeacherConfig(embed_dim=32, depth=1, dropout=.2))
            with mock.patch("dodge_learning.ppo._forward", side_effect=traced_forward):
                train_teacher(self.config(), model=model, environment_factory=FakeEnvironment)
        # One current forward per action, plus a bootstrap forward except on
        # the single death. Reusing a dropout realization would change PPO.
        self.assertEqual(sum(no_grad_calls), 13)

    def test_rollout_recomputes_outputs_after_an_inplace_parameter_edit(self):
        calls = []
        pending_edit = [False]
        edited = [False]
        original_forward = ppo._forward
        with torch.random.fork_rng(devices=[]):
            model = EntityActorCritic(EntityTeacherConfig(embed_dim=32, depth=1))

        def traced_forward(active_model, states):
            output = original_forward(active_model, states)
            if not torch.is_grad_enabled():
                calls.append(round(float(states[0].features[0, 0]) * 128))
                if len(calls) == 2:
                    pending_edit[0] = True
            return output

        def clock():
            if pending_edit[0] and not edited[0]:
                with torch.no_grad():
                    next(model.parameters()).add_(.01)
                edited[0] = True
            return 0.

        with (
            mock.patch("dodge_learning.ppo._forward", side_effect=traced_forward),
            mock.patch("dodge_learning.ppo.time.monotonic", side_effect=clock),
        ):
            train_teacher(self.config(total_frames=3, max_episode_frames=8, rollout_steps=3),
                          model=model, environment_factory=FakeEnvironment)
        self.assertTrue(edited[0])
        self.assertEqual(calls, [64, 65, 65, 66, 67])

    def test_private_rngs_and_model_initialization_preserve_callers_random_state(self):
        torch_state = torch.random.get_rng_state().clone()
        numpy_state = np.random.get_state()
        python_state = random.getstate()
        threads = torch.get_num_threads()
        first = train_teacher(self.config(), environment_factory=FakeEnvironment)
        second = train_teacher(self.config(), environment_factory=FakeEnvironment)
        torch.testing.assert_close(torch.random.get_rng_state(), torch_state)
        current_numpy = np.random.get_state()
        self.assertEqual(numpy_state[0], current_numpy[0])
        np.testing.assert_array_equal(numpy_state[1], current_numpy[1])
        self.assertEqual(numpy_state[2:], current_numpy[2:])
        self.assertEqual(random.getstate(), python_state)
        self.assertEqual(torch.get_num_threads(), threads)
        self.assertEqual(FakeEnvironment.instances[0].actions, FakeEnvironment.instances[1].actions)
        for name, parameter in first.model.state_dict().items():
            torch.testing.assert_close(parameter, second.model.state_dict()[name], rtol=0, atol=0)

    def test_wall_time_limit_during_collection_reports_only_performed_frames(self):
        now = [0.0]

        class TimedEnvironment(FakeEnvironment):
            def step(self, action):
                result = super().step(action)
                now[0] += 1.0
                return result

        with mock.patch("dodge_learning.ppo.time.monotonic", side_effect=lambda: now[0]):
            result = train_teacher(self.config(max_seconds=2), environment_factory=TimedEnvironment)
        self.assertEqual(result.metrics["frames_collected"], 2)
        self.assertEqual(result.metrics["optimizer_steps"], 0)
        self.assertEqual(result.metrics["unoptimized_frames"], 2)
        self.assertEqual(result.metrics["stop_reason"], "time_budget")

    def test_wall_time_limit_during_optimization_stops_additional_updates(self):
        now = [0.0]
        original_step = torch.optim.Adam.step

        def timed_step(optimizer, *args, **kwargs):
            result = original_step(optimizer, *args, **kwargs)
            now[0] = 2.0
            return result

        with (
            mock.patch("dodge_learning.ppo.time.monotonic", side_effect=lambda: now[0]),
            mock.patch.object(torch.optim.Adam, "step", timed_step),
        ):
            result = train_teacher(self.config(max_seconds=1, minibatch_size=2, epochs=2),
                                   environment_factory=FakeEnvironment)
        self.assertEqual(result.metrics["frames_collected"], 4)
        self.assertEqual(result.metrics["optimizer_steps"], 1)
        self.assertEqual(result.metrics["updates"], 1)
        self.assertEqual(result.metrics["unoptimized_frames"], 2)
        self.assertEqual(result.metrics["stop_reason"], "time_budget")

    def test_schema_or_cadence_failures_close_environment_and_restore_threads(self):
        class WrongSchema(FakeEnvironment):
            def observation(self):
                result = super().observation()
                result["info"]["provenance"]["feature_schema_version"] = 1
                return result

        class SkipsFrames(FakeEnvironment):
            def step(self, action):
                result = super().step(action)
                result["info"]["elapsed_native_frames"] = 2
                return result

        threads = torch.get_num_threads()
        for factory in (WrongSchema, SkipsFrames):
            with self.subTest(factory=factory), self.assertRaises(RuntimeError):
                train_teacher(self.config(), environment_factory=factory)
            self.assertTrue(FakeEnvironment.instances[-1].closed)
            self.assertEqual(torch.get_num_threads(), threads)

    @unittest.skipUnless(HAS_NATIVE, "build the optional native bridge")
    def test_real_native_tiny_training_changes_finite_weights(self):
        with torch.random.fork_rng(devices=[]):
            torch.random.default_generator.manual_seed(17)
            model = StateActorCritic(TeacherConfig(hidden_dim=32, entity_dim=16))
        initial = {name: parameter.detach().clone() for name, parameter in model.named_parameters()}
        result = train_teacher(self.config(total_frames=8, max_episode_frames=4), model=model)
        self.assertEqual(result.metrics["frames_collected"], 8)
        self.assertEqual(result.metrics["updates"], 2)
        self.assertEqual(result.metrics["truncated_episodes"], 2)
        self.assertTrue(any(not torch.equal(parameter, initial[name])
                            for name, parameter in model.named_parameters()))
        self.assertTrue(all(bool(torch.isfinite(parameter).all()) for parameter in model.parameters()))
        json.dumps(result.metrics, allow_nan=False)


@unittest.skipUnless(HAS_MODELS, "install the optional PyTorch model extra")
class CriticTrunkGradientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.previous_threads)

    def model_and_states(self):
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(37)
            model = EntityActorCritic(EntityTeacherConfig(embed_dim=32, depth=1))
        observation = FakeEnvironment(
            seed=1000, max_episode_frames=4, action_repeat=1, discount=.99,
        ).observation()["privileged_state"]
        observation["entities"].append({
            "features": [.75, .5, -.1, 0., .3] + [0.] * 27,
            "kind": 1, "bounds": [96., 64., 100., 68.], "spatial": True,
        })
        first = encode_entities(observation)
        observation["entities"][1]["features"][0] = .25
        observation["entities"][1]["bounds"] = [32., 64., 36., 68.]
        second = encode_entities(observation)
        return model, [first, second]

    def test_detached_critic_matches_values_and_only_trains_its_head(self):
        model, states = self.model_and_states()
        regular_logits, regular_values = ppo._forward(model, states)
        logits, values = ppo._forward(model, states, critic_trunk_grad=False)
        torch.testing.assert_close(logits, regular_logits, rtol=0, atol=0)
        torch.testing.assert_close(values, regular_values, rtol=0, atol=0)
        (values - torch.tensor([2., -2.])).square().mean().backward()
        for name, parameter in model.named_parameters():
            with self.subTest(parameter=name):
                if name.startswith("value."):
                    self.assertIsNotNone(parameter.grad)
                    self.assertGreater(float(parameter.grad.abs().sum()), 0)
                else:
                    self.assertIsNone(parameter.grad)

    def test_default_critic_still_trains_transformer_and_detached_actor_keeps_attention_gradients(self):
        model, states = self.model_and_states()
        _, values = ppo._forward(model, states)
        (values - torch.tensor([2., -2.])).square().mean().backward()
        self.assertGreater(float(model.entity_projection.weight.grad.abs().sum()), 0)
        self.assertGreater(float(model.blocks[0].attention.in_proj_weight.grad.abs().sum()), 0)
        self.assertIsNone(model.actor.weight.grad)

        model.zero_grad(set_to_none=True)
        logits, values = ppo._forward(model, states, critic_trunk_grad=False)
        loss = torch.nn.functional.cross_entropy(logits, torch.tensor([1, 2]))
        loss = loss + (values - torch.tensor([2., -2.])).square().mean()
        loss.backward()
        self.assertGreater(float(model.actor.weight.grad.abs().sum()), 0)
        self.assertGreater(float(model.entity_projection.weight.grad.abs().sum()), 0)
        # Query/key gradients demonstrate that the actor can still learn which
        # entities receive attention, not merely change projected values.
        attention_gradient = model.blocks[0].attention.in_proj_weight.grad
        self.assertGreater(float(attention_gradient[:64].abs().sum()), 0)
        self.assertGreater(float(model.value.weight.grad.abs().sum()), 0)

    def test_unsupported_models_fail_before_environment_construction(self):
        config = PPOConfig(total_frames=4, critic_trunk_grad=False)
        factory = mock.Mock(side_effect=AssertionError("must reject before creating an environment"))
        with torch.random.fork_rng(devices=[]):
            legacy = StateActorCritic(TeacherConfig(32, 16))
            custom = torch.nn.Linear(2, 2)
        for model, architecture in ((legacy, None), (custom, None), (None, "legacy_mlp")):
            with self.subTest(model=type(model).__name__, architecture=architecture):
                with self.assertRaisesRegex(ValueError, "requires an EntityActorCritic"):
                    train_teacher(config, model=model, architecture=architecture, environment_factory=factory)
        factory.assert_not_called()

    def test_detachment_option_reaches_only_optimization_forwards(self):
        calls = []
        original_forward = ppo._forward

        def traced_forward(model, states, **kwargs):
            calls.append((torch.is_grad_enabled(), kwargs))
            return original_forward(model, states, **kwargs)

        config = PPOConfig(
            total_frames=4, max_seconds=30, rollout_steps=4, epochs=1,
            minibatch_size=4, max_episode_frames=4, critic_trunk_grad=False,
        )
        with mock.patch("dodge_learning.ppo._forward", side_effect=traced_forward):
            result = train_teacher(config, environment_factory=FakeEnvironment)
        self.assertFalse(result.metrics["critic_trunk_grad"])
        self.assertEqual([kwargs for gradients, kwargs in calls if gradients], [{"critic_trunk_grad": False}])
        self.assertTrue(all(not kwargs for gradients, kwargs in calls if not gradients))

    @unittest.skipUnless(HAS_NATIVE, "build the optional native bridge")
    def test_cli_records_critic_detachment_without_running_a_training_campaign(self):
        from dodge_learning.checkpoints import load_teacher_checkpoint
        from dodge_learning.ppo import TrainingResult
        from dodge_learning.teacher_run import main

        def synthetic_result(config, *, model, **kwargs):
            return TrainingResult(model, {}, {
                "provenance": {"feature_schema_version": 2, "privileged_schema_version": 1},
                "critic_trunk_grad": config.critic_trunk_grad,
            }, config)

        with tempfile.TemporaryDirectory() as directory:
            for detached in (False, True):
                output = Path(directory) / ("detached" if detached else "default")
                arguments = [
                    "train", "--output-dir", str(output), "--frames", "4",
                    "--embed-dim", "32", "--depth", "1",
                ]
                if detached:
                    arguments.append("--detach-critic-trunk")
                with (
                    mock.patch("dodge_learning.ppo.train_teacher", side_effect=synthetic_result),
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(arguments), 0)
                configuration = json.loads((output / "config.json").read_text())
                loaded = load_teacher_checkpoint(output / "teacher.pt")
                self.assertIs(configuration["critic_trunk_grad"], not detached)
                self.assertIs(loaded.metadata["training_config"]["critic_trunk_grad"], not detached)
                self.assertIs(loaded.metadata["metrics"]["critic_trunk_grad"], not detached)


if __name__ == "__main__":
    unittest.main()
