"""Build source-only observability findings and proposed metrics; never run an agent."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


prior_path = ROOT / "learning/runs/v2/priority-runlist-parent-20261030-r4/heuristic-shield-observability-audit.json"
prior = json.loads(prior_path.read_text())
for path, digest in prior["input_pins"].items():
    assert sha(ROOT / path) == digest, path
fields = [
    dict(read="player x/y/vx/vy/size", source="m0_policy.rs:201,238-241,293,298-323,335-424",
         admitted="global_feats0..4 and public movement/clamp constants", disposition="Available approximately from scaled float arrays; no exact fixed-point parity claim."),
    dict(read="every enemy x/y/size/personality", source="m0_policy.rs:203-214",
         admitted="visible admitted entity geometry/types only, at most64 enemy tokens", disposition="Complete FullState list forbidden for teacher decisions/labels; visible coarse type does not license hidden personality fields."),
    dict(read="enemy vx/vy/speed; global speed/freeze", source="m0_policy.rs:218-229",
         admitted="global speed/freeze exist; entity dx/dy are measured geometry changes", disposition="Do not replace unknown measured motion with analytic enemy velocity. First-sample zero is not certified stillness."),
    dict(read="active_pattern and full pattern rect list", source="m0_policy.rs:129-133,164,178-181,247-248",
         admitted="admitted rectangle tokens and visible-pattern flag only", disposition="No raw active-pattern identity, inactive catalog or hidden/offscreen rectangle list in shield, labeler or features."),
    dict(read="pattern.id, pattern_type and exact offscreen-control tuple", source="m0_policy.rs:252-259",
         admitted="No pattern ID; admission is geometry/visibility-based", disposition="Pattern23 exception cannot be copied into an observable expert."),
    dict(read="rect x/y/width/height/sh; raw-frame index-bound history", source="m0_policy.rs:160-197,261-280",
         admitted="admitted geometry/measured deltas/until_lethal/lethal_now only", disposition="No raw sh, hidden phase/type lookup or internal stable indices. History must derive from admitted observations available to the intended student."),
    dict(read="PrivateRng", source="m0_policy.rs:289-294",
         admitted="No environment RNG", disposition="Only Random baseline draws here; AabbDodger branch does not draw environment RNG or simulate the true future. Its analytic forecast is still richer-information."),
    dict(read="12-frame action forecast and4px clearance", source="m0_policy.rs:335-424",
         admitted="Registered public physics plus admitted geometry/measured motion", disposition="Predicting an approximate future is allowed; actual engine-future rollouts are diagnostic only."),
]
audit = dict(schema="dodge_teacher_observability_recheck_v6", record="DODGE-045",
             status="source_recheck_complete_original_heuristic_ineligible_for_teacher_actions_or_labels",
             prior_audit_path=str(prior_path.relative_to(ROOT)), prior_audit_sha256=sha(prior_path),
             prior_source_pins_unchanged=True, field_mapping=fields,
             source_pins={**prior["input_pins"], "docs/v2-environment-contract.md": sha(ROOT / "docs/v2-environment-contract.md")},
             controlling_rule="No future, hidden timers, native RNG, pattern IDs, seed identities or offscreen hidden geometry may affect teacher inputs, shield decisions or training labels/targets.",
             correction="Supersede only the old decision.same_information_imitation clause allowing a separate privileged-label proposal. Under Taylor's current goal, that route is excluded. Preserve old audit bytes.",
             actor_critic="Current actor/value heads share the admitted-input latent (teacher.py:145-175). Separate critics retain this input boundary while value distillation is planned.",
             diagnostic_boundary="DODGE-004 true-future branches/oracle scores, chosen actions, safety masks and values remain diagnostic-only; never labels, auxiliary targets, imitation/DAgger targets or reward-shaping signals. Historical start-state selection does not license privileged action labels.",
             limitation="Static field mapping is not a proof that every float32 feature is recoverable from a particular pixel stack. Exact fixed-point values, measured-history cadence and any additional state require provenance/history alignment review before a new teacher contract.",
             runtime_tests=0, native_games=0, labels_generated=0, optimizer_steps=0)
save("observability-recheck.json", audit)

contract = dict(
    schema="dodge_teacher_distillation_and_executor_noise_proposal_v6", record="DODGE-046",
    status="proposal_only_no_launch_authority", training_authorized=False, evaluation_authorized=False,
    teacher_goal="Maximize teacher quality under the admitted short-history observation boundary, including robustness and useful soft labels for a future vision student.",
    provenance=dict(
        allowed_inputs=["global_feats", "entity_feats", "entity_types", "entity_mask"],
        allowed_derivations="Geometry/rays/grids/relative-closing velocity and finite action history from admitted entities, measured motion and registered public physics only. No complete-world queries or hidden index tracking.",
        history="Declare finite causal history, sampling cadence, masks and padding; align with the student's available frames/actions. Do not silently add privileged or indefinite recurrent memory.",
        forbidden=["actual future engine state", "hidden timers", "environment RNG/state/seed IDs", "pattern IDs/catalog/hidden phase fields", "offscreen hidden geometry", "diagnostic cause labels as features/targets"],
        critic="Same admitted boundary as actor while value is a distillation target; no privileged critic via encoder separation.",
        snapshot="Opaque simulator/RNG state may be stored/restored for continuity and diagnostics. Policy, labeler and shield cannot read it. Start-state prioritization does not authorize oracle supervision.",
        eligibility="Original FullState AABB remains a disclosed richer-information reference only. Shield/labeler/imitation require a separately reviewed pure-observation expert and its own accepted evaluation.",
        future_gates=["Dependency allowlist: pure arrays/history/constants; no FullState/native-future/RNG access",
                      "Identical admitted arrays/history give identical logits/masks/labels under fixed sampler state despite hidden-state changes",
                      "Visibility/cap/unknown-motion cases and all-safe/empty-mask parity",
                      "Separate diagnostic artifact schema; loader rejects oracle/full-state label provenance",
                      "Actor/value/auxiliary-target provenance and pixel/history alignment review"]),
    execution=dict(
        clean_selector="sampled categorical at temperature1; K1 common primary, actual deployment K separately frozen",
        conditions=[dict(id="clean", epsilon=0, raw_frame_delay=0),
                    dict(id="epsilon_001", epsilon=0.01, raw_frame_delay=0),
                    dict(id="epsilon_005", epsilon=0.05, raw_frame_delay=0),
                    dict(id="delay_1", epsilon=0, raw_frame_delay=1),
                    dict(id="delay_4", epsilon=0, raw_frame_delay=4)],
        epsilon="At each policy-decision boundary, independently replace the intended movement action with a uniform draw over all9 actions with probability epsilon. A draw can equal the intended action; report actual changed-action fraction separately.",
        delay="Policy observes at its normal decision times. Queue intended actions for execution after exactly d raw frames; hold the prior applied action until due. Start each episode neutral with empty queue; discard its pending actions on termination/reset. No hidden future correction or dropped intermediate action. Raw-frame stepping/queue parity must be implemented first.",
        pairing="Counter-based domain-separated policy and perturbation streams per(game seed, decision ordinal, condition); independent of vector slot and episode completion order. Share coupling across models. Noise RNG is external executor randomness, never native-world RNG or a policy input.",
        zero_noise="epsilon0/delay0 must preserve baseline actions, RNG use and counters; deterministic tests before any approved games.",
        frequency="Epsilon is per decision, so K1/K4 perturbation rates per game-second differ. Report decisions, raw frames, realized perturbations and delays; no equal-noise-dose claim across K.",
        no_combinations="Epsilon and delay conditions separate; no implicit Cartesian combination or tuning on exposed cohorts."),
    standing_metrics=dict(
        survival=["Worst", "marginal Q1 bottom-quarter mean", "Mean", "marginal Q4 top-quarter mean", "Best", "alive-frame milestones1000/3000/6000/12000/18000", "early-death fraction"],
        switches="Log intended policy-action, post-shield selected-action, and raw-frame executed-action switches separately. Numerator/denominator only within live episodes; carry across rollouts, exclude resets and neutral initialization. Report decision-rate and per1000-raw-frame measures; no queue boundary counted twice.",
        contrasts="Noise-minus-clean Q1/Mean and normalized retention; sort each condition separately before tail means. Shared-game-seed bootstrap2000 draws across every model/condition; actual fractions and per-model/per-training-replica results retained.",
        caveats="256-game monitoring panels have only64 observations per tail and are diagnostic. Noise proxies do not replace evaluation on an actual student's state distribution or establish calibrated probabilities.",
        scope="These are standing endpoint/entry/monitor/final evaluation panels; numerical optimization telemetry remains every update. No noise-driven LR/entropy/controller adjustment during the long run."),
    entropy=dict(
        schedules="Keep constant0.01, constant0.001 and registered0.01-to0.001 alternatives. Evaluate survival, noise robustness and soft-label quality together; lower entropy/jitter is not automatically better and uniform labels are not automatically useful.",
        distributions="Record original teacher categorical probabilities and post-shield renormalized target probabilities separately, with masks/fallback provenance. Specify which is distilled; no oracle sharpening or best-future-action one-hot labels.",
        diagnostics=["per-state entropy and H/log9", "maximum action probability", "top-two probability gap", "effective support exp(H)", "adjacent-state policy-distribution change", "intended versus executed switch rates"],
        weighting="Report per-episode averages plus pooled state counts; compare schedules on a fixed registered admitted-state bank from allowed trajectories as well as own rollouts, to separate occupancy shifts. Preserve target zeros/float precision and temperature1; any smoothing/temperature change is a separate registered intervention.",
        inference="Entropy is not calibration. No target entropy, distillation benefit or ranking inferred without measurements. No actual student training in this proposal."),
    budgets=dict(
        semantics="Additional proposed hard ceilings, not measured forecasts or authority. Old P4/P5 JSON and caps stay unchanged. New supplement requires source/review/resource/lease gates and explicit approval. Same6GiB separate RSS/MPS and one MPS job.",
        pilot=dict(id="A9", checkpoint=420, existing_seed_count=1024, seed_subset="first1024 ascending consumed3657433088..3657435135", K=[1,4],
                   conditions=5, total_panel_games=10240, new_clean_games=2048, new_perturbed_games=8192,
                   work_seconds=10800, receipt_seconds=540, total_ceiling_seconds=11340,
                   clean_gate="Clean rows are counted anew under the same registered sampler/loop as perturbations. Do not reuse older global/batched-sampler rows as an exact control for a new per-game sampler.",
                   readiness="needs_raw_frame_executor_source_and_qualification_not_launch_ready"),
        entry_supplement=dict(models=5, perturbed_conditions=4, game_seeds_subset=256, extra_games=5120,
                              shards=2, work_seconds=7200, receipt_seconds=360, total_ceiling_seconds=7560),
        monitoring_supplement=dict(looks=6, models_per_look=4, perturbed_conditions=4, game_seeds_subset_per_look=256,
                                   extra_games_per_look=4096, total_extra_games=24576, shards=6,
                                   work_seconds=21600, receipt_seconds=1080, total_ceiling_seconds=22680),
        final_supplement=dict(models=7, perturbed_conditions=4, game_seeds_subset=512, extra_games=14336,
                              shards=4, work_seconds=14400, receipt_seconds=720, total_ceiling_seconds=15120),
        cohort_use="Noise panels use fixed ascending subsets of the same stage-specific clean cohort; clean subset statistics must be recomputed for paired noise contrasts. No additional distinct evaluation seeds. Shared seeds across conditions are intentional pairing, not adaptive cohort reuse.",
        ranking="Noise panels descriptive unless selection/stop thresholds prospectively registered before opening games. Clean P5 Q1/Mean progress/stop criteria unchanged; no posthoc noise gate.",
        new_seed_reservations=0, cohorts_opened=0, games_run=0),
    expected="Epsilon actions and delay may reveal compounding-error sensitivity; the direction and relative ordering of policies/schedules are unobserved. An observation-only expert may be weaker than FullState, which cannot justify relaxing the information boundary.")
b = contract["budgets"]
assert b["pilot"]["total_panel_games"] == 2 * 5 * 1024
assert b["pilot"]["new_perturbed_games"] == 2 * 4 * 1024
assert b["entry_supplement"]["extra_games"] == 5 * 4 * 256
assert b["monitoring_supplement"]["total_extra_games"] == 6 * 4 * 4 * 256
assert b["final_supplement"]["extra_games"] == 7 * 4 * 512
b["revised_phase0_ceiling_seconds_if_A9_approved"] = 27300 + 11340
b["long_run_supplement_seconds"] = 22680 + 15120
b["revised_long_run_ceiling_seconds_if_approved"] = 103800 + 22680 + 15120
b["revised_all_missing_entry_ceiling_seconds_if_approved"] = 51480 + 7560
b["revised_controls_only_entry_ceiling_seconds_if_approved"] = 29520 + 7560
assert b["revised_long_run_ceiling_seconds_if_approved"] == 141600
save("teacher-metrics-proposal-v6.json", contract)
print(json.dumps(dict(source_pins_rechecked=len(prior["input_pins"]), runtime_launches=0,
                      long_run_with_noise_ceiling_seconds=141600, new_evaluation_seeds=0)))
