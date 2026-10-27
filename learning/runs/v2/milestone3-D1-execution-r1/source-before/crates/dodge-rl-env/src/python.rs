//! Python owns only returned arrays. Detached work touches Rust storage only.
use numpy::{
    Element, IntoPyArray, PyArray1, PyArrayMethods,
    ndarray::{ArrayD, IxDyn},
};
use pyo3::{
    exceptions::{PyRuntimeError, PyTypeError, PyValueError},
    prelude::*,
    types::{PyBool, PyDict, PyInt, PyList, PyTuple},
};

use crate::{
    BatchInfo, Diagnostics, EnvConfig, EnvError, EpisodeInfo, ObservationBatch, ResetBatch,
    SeedMetadata, SeedMode, StepBatch, VecDodgeEnv,
};

fn env_error(error: EnvError) -> PyErr {
    match error {
        EnvError::Config(_)
        | EnvError::ActionShape { .. }
        | EnvError::ActionId { .. }
        | EnvError::SlotIndex(_)
        | EnvError::DuplicateReset(_)
        | EnvError::SlotNotEnded(_)
        | EnvError::SlotEnded(_) => PyValueError::new_err(error.to_string()),
        _ => PyRuntimeError::new_err(error.to_string()),
    }
}

/// Accept exact 1D int64 arrays, or lists/tuples of Python integers. Copy every
/// element before detach. No NumPy guard, view, or Python input enters Rayon.
fn integer_input(input: &Bound<'_, PyAny>) -> PyResult<Vec<i64>> {
    if let Ok(array) = input.cast::<PyArray1<i64>>() {
        let readonly = array
            .try_readonly()
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        return Ok(readonly.as_array().iter().copied().collect());
    }
    if !input.is_instance_of::<PyList>() && !input.is_instance_of::<PyTuple>() {
        return Err(PyTypeError::new_err(
            "expected a 1D numpy int64 array or Python integer list/tuple",
        ));
    }
    input
        .try_iter()?
        .map(|item| {
            let item = item?;
            if item.is_instance_of::<PyBool>() || !item.is_instance_of::<PyInt>() {
                return Err(PyTypeError::new_err(
                    "every element must be a Python integer (not bool)",
                ));
            }
            item.extract::<i64>()
        })
        .collect()
}

fn array<'py, T: Element>(
    py: Python<'py>,
    data: Vec<T>,
    shape: &[usize],
) -> PyResult<Bound<'py, numpy::PyArrayDyn<T>>> {
    let owned = ArrayD::from_shape_vec(IxDyn(shape), data)
        .map_err(|e| PyRuntimeError::new_err(format!("native array shape: {e}")))?;
    // NumPy retains this independent Rust allocation through its base owner.
    Ok(owned.into_pyarray(py))
}

fn diagnostics<'py>(py: Python<'py>, value: Diagnostics) -> PyResult<Bound<'py, PyDict>> {
    let out = PyDict::new(py);
    out.set_item("raw_history_samples", value.raw_history_samples)?;
    out.set_item("unknown_enemy_samples", value.unknown_enemy_samples)?;
    out.set_item("unknown_rectangle_samples", value.unknown_rectangle_samples)?;
    out.set_item("unknown_phase_samples", value.unknown_phase_samples)?;
    out.set_item("admitted_enemies", value.admitted_enemies)?;
    out.set_item("admitted_rectangles", value.admitted_rectangles)?;
    out.set_item("onscreen_warnings", value.onscreen_warnings)?;
    out.set_item("dropped_enemies", value.dropped_enemies)?;
    out.set_item("dropped_enemy_total", value.dropped_enemy_total)?;
    out.set_item("inverted_boxes", value.inverted_boxes)?;
    out.set_item("inverted_axes", value.inverted_axes)?;
    Ok(out)
}

fn seed<'py>(py: Python<'py>, value: SeedMetadata) -> PyResult<Bound<'py, PyDict>> {
    let out = PyDict::new(py);
    out.set_item("slot", value.slot)?;
    out.set_item("episode", value.episode)?;
    out.set_item("counter", value.counter)?;
    out.set_item("actual_seed", value.actual_seed)?;
    out.set_item("evaluation", value.evaluation)?;
    Ok(out)
}

fn episode<'py>(py: Python<'py>, value: EpisodeInfo) -> PyResult<Bound<'py, PyDict>> {
    let out = PyDict::new(py);
    out.set_item("seed", seed(py, value.seed)?)?;
    out.set_item("startup_frames", value.startup_frames)?;
    out.set_item("gameplay_frames", value.gameplay_frames)?;
    out.set_item("alive_frames", value.alive_frames)?;
    out.set_item("score_raw_fixed", value.score_raw_fixed)?;
    out.set_item("score", value.score)?;
    out.set_item("score_delta_sum_raw_fixed", value.score_delta_sum_raw_fixed)?;
    out.set_item("objective_return", value.objective_return)?;
    out.set_item("terminated", value.terminated)?;
    out.set_item("truncated", value.truncated)?;
    out.set_item("bootstrap", value.bootstrap)?;
    out.set_item("diagnostics", diagnostics(py, value.diagnostics)?)?;
    Ok(out)
}

fn episodes<'py>(py: Python<'py>, values: Vec<EpisodeInfo>) -> PyResult<Bound<'py, PyList>> {
    let out = PyList::empty(py);
    for value in values {
        out.append(episode(py, value)?)?;
    }
    Ok(out)
}

fn observation<'py>(py: Python<'py>, value: ObservationBatch) -> PyResult<Bound<'py, PyDict>> {
    let b = value.batch_size();
    let out = PyDict::new(py);
    out.set_item("global_feats", array(py, value.global_feats, &[b, 1, 14])?)?;
    out.set_item("entity_feats", array(py, value.entity_feats, &[b, 80, 16])?)?;
    out.set_item("entity_types", array(py, value.entity_types, &[b, 80])?)?;
    out.set_item("entity_mask", array(py, value.entity_mask, &[b, 80])?)?;
    out.set_item("indices", value.indices.into_pyarray(py))?;
    match value.pixels {
        Some(v) => out.set_item("pixels", array(py, v, &[b, 4, 128, 128])?)?,
        None => out.set_item("pixels", py.None())?,
    }
    match value.auxiliary {
        Some(v) => out.set_item("auxiliary", array(py, v, &[b, 5, 16, 16])?)?,
        None => out.set_item("auxiliary", py.None())?,
    }
    out.set_item("pixel_valid", value.pixel_valid.into_pyarray(py))?;
    out.set_item(
        "pixel_aux_pair_valid",
        value.pixel_aux_pair_valid.into_pyarray(py),
    )?;
    let diags = PyList::empty(py);
    for value in value.diagnostics {
        diags.append(diagnostics(py, value)?)?;
    }
    out.set_item("diagnostics", diags)?;
    Ok(out)
}

fn step_batch<'py>(py: Python<'py>, value: StepBatch) -> PyResult<Bound<'py, PyDict>> {
    let out = PyDict::new(py);
    out.set_item("observations", observation(py, value.observations)?)?;
    out.set_item("rewards", value.rewards.into_pyarray(py))?;
    out.set_item(
        "score_delta_raw_fixed",
        value.score_delta_raw_fixed.into_pyarray(py),
    )?;
    out.set_item("alive_raw_frames", value.alive_raw_frames.into_pyarray(py))?;
    out.set_item(
        "elapsed_raw_frames",
        value.elapsed_raw_frames.into_pyarray(py),
    )?;
    out.set_item("terminated", value.terminated.into_pyarray(py))?;
    out.set_item("truncated", value.truncated.into_pyarray(py))?;
    out.set_item("info", episodes(py, value.info)?)?;
    Ok(out)
}

fn reset_batch<'py>(py: Python<'py>, value: ResetBatch) -> PyResult<Bound<'py, PyDict>> {
    let out = PyDict::new(py);
    out.set_item("observations", observation(py, value.observations)?)?;
    out.set_item("info", episodes(py, value.info)?)?;
    Ok(out)
}

fn batch_info<'py>(py: Python<'py>, value: BatchInfo) -> PyResult<Bound<'py, PyDict>> {
    let out = PyDict::new(py);
    let c = value.config;
    out.set_item("batch_size", c.batch_size)?;
    out.set_item("action_repeat", c.action_repeat)?;
    out.set_item("difficulty", c.difficulty)?;
    out.set_item("patterns_enabled", c.patterns_enabled)?;
    out.set_item("powerups_enabled", c.powerups_enabled)?;
    out.set_item("raw_frame_cap", c.raw_frame_cap)?;
    out.set_item("num_threads", c.num_threads)?;
    out.set_item("chunk_size", c.chunk_size)?;
    out.set_item("render_pixels", c.render_pixels)?;
    out.set_item("auxiliary_targets", c.auxiliary_targets)?;
    let mode = PyDict::new(py);
    match c.seed_mode {
        SeedMode::Training { run_seed } => {
            mode.set_item("mode", "training")?;
            mode.set_item("run_seed", run_seed)?;
            out.set_item("run_seed", run_seed)?;
            out.set_item("seeds_by_slot", py.None())?;
        }
        SeedMode::Evaluation { seeds_by_slot } => {
            mode.set_item("mode", "evaluation")?;
            mode.set_item("seeds_by_slot", &seeds_by_slot)?;
            out.set_item("run_seed", py.None())?;
            out.set_item("seeds_by_slot", seeds_by_slot)?;
        }
    }
    out.set_item("seed_mode", mode)?;
    out.set_item("additional_excluded_seed_ranges", c.excluded_seed_ranges)?;
    out.set_item(
        "excluded_seed_ranges",
        &value.effective_excluded_seed_ranges,
    )?;
    out.set_item(
        "effective_excluded_seed_ranges",
        value.effective_excluded_seed_ranges,
    )?;
    out.set_item("initial_episode_indices", value.initial_episode_indices)?;
    out.set_item("seed_stream_version", value.seed_stream_version)?;
    out.set_item("seed_exclusion_version", value.seed_exclusion_version)?;
    out.set_item("motion_version", value.motion_version)?;
    out.set_item(
        "observation_schema_version",
        "dodge_global14_entity80x16_v2_r2",
    )?;
    out.set_item("binding_api_version", "dodge_vec_owned_v1")?;
    out.set_item(
        "reward_version",
        "score_plus_0.01_alive_minus_5_termination_v1",
    )?;
    out.set_item(
        "admission_version",
        "current_conservative_renderer_footprint_v1",
    )?;
    out.set_item("global_shape", [1, 14])?;
    out.set_item("entity_shape", [80, 16])?;
    out.set_item("pixel_shape", [4, 128, 128])?;
    out.set_item("auxiliary_shape", [5, 16, 16])?;
    out.set_item(
        "theme_background_shadow",
        value.theme_background_shadow.map(u32::from),
    )?;
    out.set_item(
        "initial_highscores_raw_fixed",
        value.initial_highscores_raw_fixed,
    )?;
    Ok(out)
}

#[pyclass(name = "VecDodgeEnv", module = "dodge_rl._native")]
struct PyVecDodgeEnv {
    inner: VecDodgeEnv,
}

#[pymethods]
impl PyVecDodgeEnv {
    #[new]
    #[pyo3(signature = (batch_size=1, action_repeat=4, difficulty=2, patterns_enabled=true, powerups_enabled=true, raw_frame_cap=18_000, num_threads=1, chunk_size=8, render_pixels=false, auxiliary_targets=false, run_seed=0, seeds_by_slot=None, excluded_seed_ranges=None, initial_episode_indices=None))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        batch_size: usize,
        action_repeat: u8,
        difficulty: u8,
        patterns_enabled: bool,
        powerups_enabled: bool,
        raw_frame_cap: u32,
        num_threads: usize,
        chunk_size: usize,
        render_pixels: bool,
        auxiliary_targets: bool,
        run_seed: u64,
        seeds_by_slot: Option<Vec<Vec<u32>>>,
        excluded_seed_ranges: Option<Vec<(u32, u32)>>,
        initial_episode_indices: Option<Vec<u64>>,
    ) -> PyResult<Self> {
        let config = EnvConfig {
            batch_size,
            action_repeat,
            difficulty,
            patterns_enabled,
            powerups_enabled,
            raw_frame_cap,
            num_threads,
            chunk_size,
            render_pixels,
            auxiliary_targets,
            seed_mode: seeds_by_slot.map_or(SeedMode::Training { run_seed }, |seeds_by_slot| {
                SeedMode::Evaluation { seeds_by_slot }
            }),
            excluded_seed_ranges: excluded_seed_ranges.unwrap_or_default(),
            initial_episode_indices,
        };
        // Includes validation, seed preflight, NativeGame::new, bounded startup,
        // initial features, and optional rendering. No Python callbacks occur.
        let inner = py
            .detach(move || VecDodgeEnv::new(config))
            .map_err(env_error)?;
        Ok(Self { inner })
    }

    fn observations<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let value = py.detach(|| self.inner.observations()).map_err(env_error)?;
        observation(py, value)
    }

    fn step<'py>(
        &mut self,
        py: Python<'py>,
        actions: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let ids = integer_input(actions)?;
        // The input guard has been dropped. Only this owned Vec is captured.
        // Rust validates the whole request before any stable slot advances.
        let value = py.detach(|| self.inner.step(&ids)).map_err(env_error)?;
        step_batch(py, value)
    }

    fn reset_done<'py>(
        &mut self,
        py: Python<'py>,
        indices: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let indices = integer_input(indices)?
            .into_iter()
            .map(|i| {
                usize::try_from(i)
                    .map_err(|_| PyValueError::new_err("reset index must be nonnegative"))
            })
            .collect::<PyResult<Vec<_>>>()?;
        let value = py
            .detach(|| self.inner.reset_done(&indices))
            .map_err(env_error)?;
        reset_batch(py, value)
    }

    fn reset_all<'py>(&mut self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let value = py.detach(|| self.inner.reset_all()).map_err(env_error)?;
        reset_batch(py, value)
    }

    fn episode_info<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        episodes(py, self.inner.episode_info())
    }

    fn batch_info<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let out = batch_info(py, self.inner.batch_info())?;
        let next: Vec<_> = self
            .inner
            .episode_info()
            .iter()
            .map(|i| i.seed.episode.checked_add(1))
            .collect();
        out.set_item("next_episode_indices", next)?;
        Ok(out)
    }

    fn is_poisoned(&self) -> bool {
        self.inner.is_poisoned()
    }
    fn last_failures(&self) -> Vec<(usize, String)> {
        self.inner.last_failures().to_vec()
    }
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PyVecDodgeEnv>()?;
    Ok(())
}
