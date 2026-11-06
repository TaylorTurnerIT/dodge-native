use crate::velocity_flow::{CELL_COUNT, PLAYER_VALUES};
use crate::{
    EnvConfig, EnvError, ObservationBatch, ObservationKind, SeedMode, VELOCITY_FLOW_SIZE,
    VELOCITY_FLOW_VERSION, VecDodgeEnv, encode_velocity_flow,
};

fn config(observation: ObservationKind) -> EnvConfig {
    EnvConfig {
        batch_size: 4,
        action_repeat: 1,
        raw_frame_cap: 100_000,
        observation,
        ..EnvConfig::default()
    }
}

fn encode(game: &dodge_core::NativeGame) -> Vec<f32> {
    let mut out = vec![f32::NAN; VELOCITY_FLOW_SIZE];
    encode_velocity_flow(game, &mut out);
    out
}

#[test]
fn layout_constants() {
    assert_eq!(VELOCITY_FLOW_SIZE, 3076);
    assert_eq!(VELOCITY_FLOW_VERSION, "velocity_flow_3076_v1");
    assert_eq!(EnvConfig::default().observation, ObservationKind::Entity);
}

/// Bit parity with the source encoder on the games both engines play alike.
#[test]
fn matches_the_source_encoder() {
    super::source_fixtures::check(include_str!("fixtures/velocity_flow_source.txt"), encode);
}

#[test]
fn pixels_and_targets_need_the_entity_observation() {
    for (pixels, targets) in [(true, false), (false, true)] {
        let config = EnvConfig {
            render_pixels: pixels,
            auxiliary_targets: targets,
            ..config(ObservationKind::VelocityFlow)
        };
        assert_eq!(
            config.validate(),
            Err(EnvError::Config(
                "render_pixels and auxiliary_targets need the entity observation"
            ))
        );
    }
}

fn assert_rows_encode_games(env: &VecDodgeEnv, batch: &ObservationBatch) {
    let rows = batch.velocity_flow.as_deref().unwrap_or_default();
    assert_eq!(rows.len(), batch.batch_size() * VELOCITY_FLOW_SIZE);
    assert!(batch.global_feats.is_empty() && batch.entity_feats.is_empty());
    assert!(batch.entity_types.is_empty() && batch.entity_mask.is_empty());
    assert!(batch.pixels.is_none() && batch.auxiliary.is_none());
    for (row, slot) in rows.chunks(VELOCITY_FLOW_SIZE).zip(&batch.indices) {
        assert_eq!(row, encode(env.test_game(*slot)).as_slice(), "slot {slot}");
    }
}

/// Rows are the encoding of each slot's game at the end of the reset or step,
/// and dropping the entity history leaves the games themselves unchanged.
#[test]
fn steps_return_the_encoding_of_the_same_games() -> Result<(), EnvError> {
    let mut flow = VecDodgeEnv::new(config(ObservationKind::VelocityFlow))?;
    let mut entity = VecDodgeEnv::new(config(ObservationKind::Entity))?;
    assert_rows_encode_games(&flow, &flow.observations()?);
    let mut resets = 0;
    for step in 0..2_000_i64 {
        let actions = [step % 9, (step / 4) % 9, (step / 9) % 9, 0];
        let batch = flow.step(&actions)?;
        let other = entity.step(&actions)?;
        assert_rows_encode_games(&flow, &batch.observations);
        assert!(other.observations.velocity_flow.is_none());
        assert_eq!(batch.terminated, other.terminated);
        assert_eq!(batch.score_delta_raw_fixed, other.score_delta_raw_fixed);
        for slot in 0..4 {
            assert_eq!(
                flow.test_game(slot).snapshot(),
                entity.test_game(slot).snapshot(),
                "slot {slot} step {step}"
            );
        }
        let ended: Vec<usize> = (0..4)
            .filter(|i| batch.terminated[*i] || batch.truncated[*i])
            .collect();
        if !ended.is_empty() {
            let reset = flow.reset_done(&ended)?;
            assert_eq!(reset.observations.indices, ended);
            assert_rows_encode_games(&flow, &reset.observations);
            entity.reset_done(&ended)?;
            resets += 1;
        }
    }
    assert!(resets > 0);
    Ok(())
}

/// Ported from the source batch test of the same name: an empty cell carries
/// no motion, and a velocity is always that of whatever occupies its cell.
#[test]
fn velocity_observation_keeps_each_plane_aligned_with_its_cells() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        batch_size: 2,
        seed_mode: SeedMode::Evaluation {
            seeds_by_slot: vec![vec![42], vec![13]],
        },
        ..config(ObservationKind::VelocityFlow)
    })?;
    // Short enough that neither seed dies, long enough for enemies to spawn
    // and move.
    let mut last = None;
    for frame in 0..120 {
        let action = if frame % 60 < 30 { 1 } else { 8 };
        last = Some(env.step(&[action, action])?);
    }
    let batch = last.ok_or(EnvError::Contract("no step"))?;
    assert!(!batch.terminated.iter().any(|t| *t));
    let rows = batch.observations.velocity_flow.unwrap_or_default();
    let mut moving_cells = 0;
    for lane in rows.chunks(VELOCITY_FLOW_SIZE) {
        let mut planes = lane.iter().skip(PLAYER_VALUES);
        let cells: Vec<f32> = planes.by_ref().take(CELL_COUNT).copied().collect();
        let vx: Vec<f32> = planes.by_ref().take(CELL_COUNT).copied().collect();
        let vy: Vec<f32> = planes.copied().collect();
        assert_eq!(vy.len(), CELL_COUNT);
        assert!(cells.iter().any(|value| *value > 0.0));
        for ((cell, x), y) in cells.iter().zip(&vx).zip(&vy) {
            if *cell == 0.0 {
                assert_eq!((*x, *y), (0.0, 0.0));
            } else if *x != 0.0 || *y != 0.0 {
                moving_cells += 1;
            }
        }
    }
    assert!(moving_cells > 0);
    Ok(())
}
