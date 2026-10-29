"""Authenticated adapter for fresh PPO rollouts on a frozen training-only pool."""
from __future__ import annotations
import copy

class SeededTrainingAdapter:
    profile = "explicit_seeded_training_v1"
    def __init__(self, env, *, seeds_by_slot, components_by_slot, strata_by_seed,
                 training_pool_values, exclusions, rollout_steps=256,
                 gameplay_frame_target=None):
        self.env = env
        self.seeds_by_slot = [list(row) for row in seeds_by_slot]
        self.components_by_slot = [list(row) for row in components_by_slot]
        self.strata_by_seed = dict(strata_by_seed)
        self.training_pool_values = frozenset(training_pool_values)
        self.exclusions = tuple(tuple(x) for x in exclusions)
        meta = env.batch_info()
        if meta["seed_mode"]["mode"] != "evaluation" or meta["seed_mode"]["seeds_by_slot"] != self.seeds_by_slot:
            raise ValueError("native explicit seed metadata mismatch; do not relabel evaluation flag")
        self.batch_size = meta["batch_size"]
        self.action_repeat = meta["action_repeat"]
        if type(self.action_repeat) is not int or self.action_repeat not in (1, 4):
            raise ValueError("registered action repeat must be 1 or 4")
        if type(rollout_steps) is not int or rollout_steps <= 0:
            raise ValueError("rollout_steps must be a positive integer")
        if gameplay_frame_target is not None and (type(gameplay_frame_target) is not int
                                                  or gameplay_frame_target <= 0):
            raise ValueError("gameplay_frame_target must be a positive integer")
        self.rollout_steps = rollout_steps
        self.gameplay_frame_target = gameplay_frame_target
        self.max_new_seed_entries = (None if gameplay_frame_target is None else
            (gameplay_frame_target + self.batch_size - 1) // self.batch_size)
        if self.batch_size != len(self.seeds_by_slot):
            raise ValueError("seed stream slot count mismatch")
        if any(not row or any(type(seed) is not int or seed not in self.training_pool_values for seed in row)
               for row in self.seeds_by_slot):
            raise ValueError("explicit stream contains seed outside frozen training-only pool")
        if len(self.components_by_slot)!=len(self.seeds_by_slot) or any(
            len(c)!=len(s) for c,s in zip(self.components_by_slot,self.seeds_by_slot)):
            raise ValueError("sampling component stream is incomplete")
        self.completed_updates = 0
        self.pending_update = None
        self.last_decision = -1
        self.expected_reset = []
        self.consumed_actual_seeds = set()
        self.initial_startup_frames = sum(int(x["startup_frames"]) for x in env.episode_info())
        self.reset_startup_frames = 0
        self.reset_count = 0
        self.observed_native_frames = 0
        self.gameplay_frames = 0
        self.budget_reached = False
        self.observed_native_steps = 0
        self.returned_reset_startup_frames = 0
        self.returned_resets = []
        self.assignment_events = []
        self.episode_events = []
        self.event_sink = None
        self.initial_episode_indices = []
        for slot, info in enumerate(env.episode_info()):
            self._validate_active(info, slot)
            seed=info["seed"]["actual_seed"]; episode=info["seed"]["episode"]
            self.initial_episode_indices.append(episode)
            self.consumed_actual_seeds.add(seed)
            self.assignment_events.append({"slot":slot,"seed":copy.deepcopy(info["seed"]),
                "role":"training_only_pool","profile":self.profile,
                "sampling_component":self.components_by_slot[slot][episode],
                "stratum":self.strata_by_seed[seed]})

    def _emit(self, event):
        if self.event_sink is not None: self.event_sink(copy.deepcopy(event))

    def _validate_active(self, info, slot, *, active=True):
        from . import ppo
        ppo._audit_episode(info, 18000, training_pool_values=self.training_pool_values)
        seed = info["seed"]
        if seed["slot"] != slot or seed["episode"] >= len(self.seeds_by_slot[slot]):
            raise ValueError("native episode index outside registered seeded stream")
        if seed["actual_seed"] != self.seeds_by_slot[slot][seed["episode"]]:
            raise ValueError("native seed differs from frozen per-slot stream")
        if self.components_by_slot[slot][seed["episode"]] not in {"uniform","uniform_floor","hard_priority"}:
            raise ValueError("native assignment lacks registered sampling component")
        if any(low <= seed["actual_seed"] <= high for low, high in self.exclusions):
            raise ValueError("native seed intersects reserved exclusion")
        if active and (info["terminated"] or info["truncated"]
                       or info["gameplay_frames"] % self.action_repeat):
            raise ValueError("active normal-start episode boundary differs")

    def begin_update(self, update):
        if self.pending_update is not None or update != self.completed_updates + 1 or self.budget_reached:
            raise ValueError("seeded update order invalid")
        self.pending_update, self.last_decision = update, -1
        self.episode_events = []

    def before_step(self, previous, decision):
        if (self.pending_update is None or decision != self.last_decision + 1
                or decision >= self.rollout_steps or self.budget_reached):
            raise ValueError("seeded decision order invalid")
        if self.expected_reset: raise ValueError("reset still pending")
        for slot, info in enumerate(previous): self._validate_active(info, slot)

    def observe_returned_step(self, result):
        returned_frames = sum(map(int, result["elapsed_raw_frames"]))
        self.observed_native_frames += returned_frames
        self.gameplay_frames += returned_frames
        if self.gameplay_frame_target is not None:
            self.budget_reached = self.gameplay_frames >= self.gameplay_frame_target
        self.observed_native_steps += 1
        self._emit({"kind":"returned_step_cost","update":self.pending_update,
                    "decision":self.last_decision+1,"elapsed_raw_frames":list(map(int,result["elapsed_raw_frames"]))})

    def reconcile(self, result, previous, decision):
        if decision != self.last_decision + 1 or len(result["info"]) != self.batch_size:
            raise ValueError("seeded returned-step alignment differs")
        for slot, info in enumerate(result["info"]): self._validate_active(info, slot, active=False)
        self.last_decision = decision
        self.expected_reset = [i for i, info in enumerate(result["info"]) if info["terminated"] or info["truncated"]]

    def record_step(self, result, previous, decision):
        for slot in self.expected_reset:
            seed=result["info"][slot]["seed"]["actual_seed"]
            row = {"slot":slot,"seed":copy.deepcopy(result["info"][slot]["seed"]),
                   "alive_frames":result["info"][slot]["alive_frames"],
                   "gameplay_frames":result["info"][slot]["gameplay_frames"],
                   "score_raw_fixed":result["info"][slot]["score_raw_fixed"],
                   "terminated":result["info"][slot]["terminated"],
                   "truncated":result["info"][slot]["truncated"],"update":self.pending_update,
                   "decision":decision,"role":"training_only_pool",
                   "sampling_component":self.components_by_slot[slot][result["info"][slot]["seed"]["episode"]],
                   "stratum":self.strata_by_seed[seed]}
            self.episode_events.append(row)
        self._emit({"kind":"seeded_step","update":self.pending_update,"decision":decision,
                    "completed":copy.deepcopy(self.episode_events[-len(self.expected_reset):]) if self.expected_reset else []})

    def before_reset(self, indices, ended_info):
        if indices != self.expected_reset: raise ValueError("reset slots differ from returned endings")
        for slot in indices:
            next_episode = ended_info[slot]["seed"]["episode"] + 1
            if next_episode >= len(self.seeds_by_slot[slot]):
                raise ValueError("next registered seed missing")
            max_episode_exclusive = (None if self.max_new_seed_entries is None else
                self.initial_episode_indices[slot] + self.max_new_seed_entries)
            if max_episode_exclusive is not None and next_episode >= max_episode_exclusive:
                raise ValueError("frame-target worst-case seed stream bound exceeded")

    def observe_returned_reset(self, indices, reset):
        self.returned_reset_startup_frames += sum(int(x["startup_frames"]) for x in reset["info"])
        self.returned_resets.append({"update":self.pending_update,"decision":self.last_decision,
                                     "indices":list(indices),"info":copy.deepcopy(reset["info"])})
        for slot, info in zip(indices, reset["info"]): self._validate_active(info, slot)
        self._emit({"kind":"returned_reset",**self.returned_resets[-1]})

    def record_reset(self, indices, infos, decision):
        assignments=[]
        for slot,info in zip(indices,infos):
            episode=info["seed"]["episode"]; seed=info["seed"]["actual_seed"]
            self.consumed_actual_seeds.add(seed)
            self.reset_startup_frames += int(info["startup_frames"])
            self.reset_count += 1
            assignments.append({"slot":slot,"seed":copy.deepcopy(info["seed"]),
                "role":"training_only_pool","sampling_component":self.components_by_slot[slot][episode],
                "stratum":self.strata_by_seed[seed]})
        self._emit({"kind":"seeded_reset","update":self.pending_update,"decision":decision,
                    "indices":list(indices),"assignments":assignments})
        self.expected_reset=[]

    def _finish_after_ppo(self):
        decisions = self.last_decision + 1
        full_rollout = decisions == self.rollout_steps
        final_rollout = self.budget_reached and 0 < decisions <= self.rollout_steps
        if (self.pending_update is None or not (full_rollout or final_rollout)
                or (self.expected_reset and not self.budget_reached)):
            raise ValueError("finish requires full rollout or reached frame target and successful PPO")
        if self.gameplay_frame_target is not None and self.budget_reached:
            if not (self.gameplay_frame_target <= self.gameplay_frames
                    < self.gameplay_frame_target + self.batch_size * self.action_repeat):
                raise ValueError("frame target accounting exceeds one final vector call")
        self.completed_updates += 1
        result={"completed_updates":self.completed_updates,"profile":self.profile,
                "decisions":decisions,"gameplay_frames":self.gameplay_frames,
                "startup_frames":self.initial_startup_frames + self.reset_startup_frames,
                "budget_reached":self.budget_reached,
                "native_seed_mode":"evaluation_explicit_seed_list","training_pool_role":"training_only"}
        self.pending_update=None
        return result

    def snapshot(self):
        return {"profile":self.profile,"completed_updates":self.completed_updates,
                "pending_update":self.pending_update,"observed_native_frames":self.observed_native_frames,
                "observed_native_steps":self.observed_native_steps,
                "returned_reset_startup_frames":self.returned_reset_startup_frames,
                "initial_startup_frames":self.initial_startup_frames,
                "reset_startup_frames":self.reset_startup_frames,
                "reset_count":self.reset_count,
                "gameplay_frames":self.gameplay_frames,
                "gameplay_frame_target":self.gameplay_frame_target,
                "initial_episode_indices":list(self.initial_episode_indices),
                "max_new_seed_entries":self.max_new_seed_entries,
                "budget_reached":self.budget_reached,
                "consumed_actual_seeds":sorted(self.consumed_actual_seeds),
                "returned_resets":copy.deepcopy(self.returned_resets),
                "native_seed_mode":"evaluation_explicit_seed_list","training_pool_role":"training_only"}
