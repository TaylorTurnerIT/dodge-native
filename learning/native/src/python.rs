//! In-process bridge. Images, actor features, and metadata have separate keys.

use dodge_core::{Action, FrameEvent, NativeConfig, Snapshot};
use pyo3::{
    exceptions::{PyRuntimeError, PyValueError},
    prelude::*,
    types::{PyBytes, PyDict, PyList},
};

use crate::{
    EnvError, EnvironmentConfig, LearningEnv,
    observation::{FEATURE_SCHEMA_VERSION, TeacherFeatures},
    privileged::{PRIVILEGED_SCHEMA_VERSION, PrivilegedFeatures},
};

#[pyclass(name = "NativeEnvironment")]
struct PythonEnvironment {
    inner: LearningEnv,
    wire_version: u32,
    last_transition: TransitionSummary,
}

struct TransitionSummary {
    reward_sum: f32,
    discounted_reward: f32,
    bootstrap_discount: f32,
    elapsed_native_frames: u32,
    events: Vec<FrameEvent>,
}

impl Default for TransitionSummary {
    fn default() -> Self {
        Self {
            reward_sum: 0.0,
            discounted_reward: 0.0,
            bootstrap_discount: 1.0,
            elapsed_native_frames: 0,
            events: Vec::new(),
        }
    }
}

fn environment_error(error: EnvError) -> PyErr {
    match error {
        EnvError::InvalidConfig(_) | EnvError::InvalidAction(_) => {
            PyValueError::new_err(error.to_string())
        }
        _ => PyRuntimeError::new_err(error.to_string()),
    }
}

#[pymethods]
impl PythonEnvironment {
    #[new]
    #[pyo3(signature = (seed=42, max_episode_frames=18_000, action_repeat=1, discount=0.99, difficulty=2, patterns_enabled=true, powerups_enabled=true, theme_background=12, theme_shadow=1))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        seed: u32,
        max_episode_frames: u32,
        action_repeat: u32,
        discount: f32,
        difficulty: u8,
        patterns_enabled: bool,
        powerups_enabled: bool,
        theme_background: u8,
        theme_shadow: u8,
    ) -> PyResult<Self> {
        let mut game = NativeConfig::new(seed);
        game.difficulty = difficulty;
        game.patterns_enabled = patterns_enabled;
        game.powerups_enabled = powerups_enabled;
        game.theme_background = theme_background;
        game.theme_shadow = theme_shadow;
        let inner = LearningEnv::new(EnvironmentConfig {
            game,
            max_episode_frames,
            action_repeat,
            discount,
        })
        .map_err(environment_error)?;
        let bytes = inner.current().snapshot.canonical_bytes();
        let version_bytes: [u8; 4] = bytes
            .get(4..8)
            .and_then(|part| part.try_into().ok())
            .ok_or_else(|| PyRuntimeError::new_err("snapshot wire version is missing"))?;
        Ok(Self {
            inner,
            wire_version: u32::from_le_bytes(version_bytes),
            last_transition: TransitionSummary::default(),
        })
    }

    #[pyo3(signature = (seed=None))]
    fn reset(&mut self, py: Python<'_>, seed: Option<u32>) -> PyResult<Py<PyDict>> {
        self.inner
            .reset(seed.unwrap_or(self.inner.config().game.seed))
            .map_err(environment_error)?;
        self.last_transition = TransitionSummary::default();
        self.current(py)
    }

    fn current(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        self.payload(
            py,
            self.last_transition.reward_sum,
            self.last_transition.discounted_reward,
            self.last_transition.bootstrap_discount,
            self.last_transition.elapsed_native_frames,
            &self.last_transition.events,
        )
    }

    fn student_observation<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, self.inner.current().snapshot.pixels())
    }

    fn step(&mut self, py: Python<'_>, action_id: usize) -> PyResult<Py<PyDict>> {
        let step = self.inner.step(action_id).map_err(environment_error)?;
        self.last_transition = TransitionSummary {
            reward_sum: step.reward_sum,
            discounted_reward: step.discounted_reward,
            bootstrap_discount: step.bootstrap_discount,
            elapsed_native_frames: step.elapsed_native_frames,
            events: step.events,
        };
        self.current(py)
    }
}

impl PythonEnvironment {
    #[allow(clippy::too_many_arguments)]
    fn payload(
        &self,
        py: Python<'_>,
        reward_sum: f32,
        discounted_reward: f32,
        bootstrap_discount: f32,
        elapsed: u32,
        events: &[FrameEvent],
    ) -> PyResult<Py<PyDict>> {
        let frame = self.inner.current();
        let snapshot = &frame.snapshot;
        let state = snapshot.logical_state();
        let config = self.inner.config();
        let info = PyDict::new(py);
        info.set_item("frame", frame.frame)?;
        info.set_item("episode_frames", self.inner.elapsed_frames())?;
        info.set_item("elapsed_native_frames", elapsed)?;
        info.set_item("terminated", self.inner.terminated())?;
        info.set_item("truncated", self.inner.truncated())?;
        info.set_item("survival_frames", state.survival_frames)?;
        info.set_item("score", state.score.ceil().to_f32())?;
        info.set_item("score_raw", state.score.to_f32())?;
        info.set_item("pattern_completions", self.inner.pattern_completions())?;
        let pattern_metrics = PyList::empty(py);
        for metrics in self.inner.pattern_metrics() {
            let row = PyDict::new(py);
            row.set_item("id", metrics.id)?;
            row.set_item("encounters", metrics.encounters)?;
            row.set_item("exposure_frames", metrics.exposure_frames)?;
            row.set_item("completions", metrics.completions)?;
            pattern_metrics.append(row)?;
        }
        info.set_item("pattern_metrics", pattern_metrics)?;
        info.set_item("state_hash", snapshot.state_hash())?;
        info.set_item("pixel_hash", snapshot.pixel_hash())?;
        info.set_item("mode", format!("{:?}", frame.mode))?;
        info.set_item("seed", config.game.seed)?;
        info.set_item(
            "events",
            events.iter().map(|event| event.name()).collect::<Vec<_>>(),
        )?;
        let provenance = PyDict::new(py);
        provenance.set_item("adapter_version", env!("CARGO_PKG_VERSION"))?;
        provenance.set_item("feature_schema_version", FEATURE_SCHEMA_VERSION)?;
        provenance.set_item("privileged_schema_version", PRIVILEGED_SCHEMA_VERSION)?;
        provenance.set_item(
            "core_schema_version",
            snapshot.provenance().core_schema_version,
        )?;
        provenance.set_item("snapshot_wire_version", self.wire_version)?;
        provenance.set_item(
            "cartridge_sha256",
            hex(&snapshot.provenance().cartridge_sha256),
        )?;
        provenance.set_item("game_revision", env!("DODGE_GAME_REVISION"))?;
        provenance.set_item("core_source_dirty", env!("DODGE_CORE_DIRTY"))?;
        provenance.set_item(
            "action_masks",
            PyList::new(py, Action::ALL.map(Action::mask))?,
        )?;
        provenance.set_item("action_names", Action::ALL.map(Action::name))?;
        provenance.set_item("action_repeat", config.action_repeat)?;
        provenance.set_item("max_episode_frames", config.max_episode_frames)?;
        provenance.set_item("discount", config.discount)?;
        provenance.set_item("difficulty", config.game.difficulty)?;
        provenance.set_item("patterns_enabled", config.game.patterns_enabled)?;
        provenance.set_item("powerups_enabled", config.game.powerups_enabled)?;
        provenance.set_item("theme_background", config.game.theme_background)?;
        provenance.set_item("theme_shadow", config.game.theme_shadow)?;
        info.set_item("provenance", provenance)?;
        let result = PyDict::new(py);
        result.set_item("pixels", PyBytes::new(py, snapshot.pixels()))?;
        result.set_item("train_only_state", teacher_dict(py, snapshot)?)?;
        result.set_item("privileged_state", privileged_dict(py, snapshot)?)?;
        result.set_item("info", info)?;
        result.set_item("reward_sum", reward_sum)?;
        result.set_item("discounted_reward", discounted_reward)?;
        result.set_item("bootstrap_discount", bootstrap_discount)?;
        Ok(result.unbind())
    }
}

fn privileged_dict<'py>(py: Python<'py>, snapshot: &Snapshot) -> PyResult<Bound<'py, PyDict>> {
    let features = PrivilegedFeatures::from_snapshot(snapshot);
    let result = PyDict::new(py);
    result.set_item("schema_version", PRIVILEGED_SCHEMA_VERSION)?;
    result.set_item("globals", PyList::new(py, features.globals)?)?;
    result.set_item("capture_bounds", features.capture_bounds)?;
    let entities = PyList::empty(py);
    for entity in features.entities {
        let row = PyDict::new(py);
        row.set_item("features", PyList::new(py, entity.features)?)?;
        row.set_item("kind", entity.kind)?;
        row.set_item("bounds", entity.bounds)?;
        row.set_item("spatial", entity.spatial)?;
        entities.append(row)?;
    }
    result.set_item("entities", entities)?;
    Ok(result)
}

fn teacher_dict<'py>(py: Python<'py>, snapshot: &Snapshot) -> PyResult<Bound<'py, PyDict>> {
    let features = TeacherFeatures::from_snapshot(snapshot);
    let result = PyDict::new(py);
    let player = PyDict::new(py);
    for (key, value) in [
        ("x", features.player.x),
        ("y", features.player.y),
        ("vx", features.player.vx),
        ("vy", features.player.vy),
        ("size", features.player.size),
    ] {
        player.set_item(key, value)?;
    }
    result.set_item("player", player)?;
    let globals = PyDict::new(py);
    globals.set_item("speed", features.speed)?;
    globals.set_item("freeze_rate", features.freeze_rate)?;
    globals.set_item("freeze_active", features.freeze_active)?;
    result.set_item("globals", globals)?;
    let enemies = PyList::empty(py);
    for enemy in features.enemies {
        let row = PyDict::new(py);
        for (key, value) in [
            ("x", enemy.x),
            ("y", enemy.y),
            ("vx", enemy.vx),
            ("vy", enemy.vy),
            ("size", enemy.size),
        ] {
            row.set_item(key, value)?;
        }
        row.set_item("kind", enemy.kind)?;
        enemies.append(row)?;
    }
    result.set_item("enemies", enemies)?;
    let rectangles = PyList::empty(py);
    for rect in features.rectangles {
        let row = PyDict::new(py);
        for (key, value) in [
            ("x", rect.x),
            ("y", rect.y),
            ("width", rect.width),
            ("height", rect.height),
            ("dx", rect.dx),
            ("dy", rect.dy),
        ] {
            row.set_item(key, value)?;
        }
        row.set_item("solid", rect.solid)?;
        rectangles.append(row)?;
    }
    result.set_item("rectangles", rectangles)?;
    let warnings = PyList::empty(py);
    for line in features.warnings {
        let row = PyDict::new(py);
        for (key, value) in [
            ("x0", line.x0),
            ("y0", line.y0),
            ("x1", line.x1),
            ("y1", line.y1),
        ] {
            row.set_item(key, value)?;
        }
        warnings.append(row)?;
    }
    result.set_item("warnings", warnings)?;
    Ok(result)
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PythonEnvironment>()?;
    Ok(())
}
