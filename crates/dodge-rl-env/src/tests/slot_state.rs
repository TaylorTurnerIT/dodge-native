use std::cell::Cell;
use std::fmt::Write as _;

use crate::{EnvConfig, EnvError, SlotState, VecDodgeEnv};

/// Fixed-point values are exact in f64, so their raw values return.
fn raw(value: f64) -> i64 {
    (value * 65536.0) as i64
}

/// The text the source fixture was hashed from: raw values in `lane_state`'s
/// order, enemies as `E`, the pattern as `C` (or `C-`), rectangles as `R` and
/// warning lines as `W`.
fn text(state: &SlotState) -> String {
    let mut t = String::new();
    let _ = write!(
        t,
        "{} {} {} {} {} {} {} {} {}",
        raw(state.px),
        raw(state.py),
        raw(state.dpx),
        raw(state.dpy),
        raw(state.size),
        state.ftimer,
        state.fy,
        raw(state.spd),
        raw(state.frz)
    );
    for e in &state.enemies {
        let _ = write!(
            t,
            " E {} {} {} {} {} {} {}",
            raw(e.x),
            raw(e.y),
            raw(e.s),
            e.p,
            raw(e.vx),
            raw(e.vy),
            raw(e.spd)
        );
    }
    match &state.cp {
        None => t.push_str(" C-"),
        Some(cp) => {
            let _ = write!(t, " C {} {} {}", cp.id, cp.tpe, raw(cp.timer));
            for r in &cp.rects {
                let _ = write!(
                    t,
                    " R {} {} {} {} {} {} {} {}",
                    raw(r.x),
                    raw(r.y),
                    raw(r.w),
                    raw(r.h),
                    raw(r.sh),
                    raw(r.dx),
                    raw(r.dy),
                    raw(r.spd)
                );
                for (x0, y0, x1, y1) in &r.warnings {
                    let _ = write!(t, " W {} {} {} {}", raw(*x0), raw(*y0), raw(*x1), raw(*y1));
                }
            }
        }
    }
    t
}

/// Compares every field of `lane_state` on the frames where the source game
/// and this one are identical (the same frames as the other source fixtures).
#[test]
fn matches_the_source_lane_state() {
    let with_enemies = Cell::new(0);
    let with_pattern = Cell::new(0);
    let with_warnings = Cell::new(0);
    super::source_fixtures::check(include_str!("fixtures/slot_state_source.txt"), |game| {
        let state = SlotState::read(game);
        with_enemies.set(with_enemies.get() + u32::from(!state.enemies.is_empty()));
        if let Some(cp) = &state.cp {
            with_pattern.set(with_pattern.get() + 1);
            if cp.rects.iter().any(|r| !r.warnings.is_empty()) {
                with_warnings.set(with_warnings.get() + 1);
            }
        }
        super::source_fixtures::fnv_bytes(text(&state).bytes())
    });
    // The fixture exercises the nested parts, not only the player.
    assert!(with_enemies.get() > 100, "{}", with_enemies.get());
    assert!(with_pattern.get() > 100, "{}", with_pattern.get());
    assert!(with_warnings.get() > 10, "{}", with_warnings.get());
}

#[test]
fn an_environment_reads_each_slots_own_game_without_changing_it() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        batch_size: 3,
        raw_frame_cap: 100_000,
        ..EnvConfig::default()
    })?;
    for step in 0..120_i64 {
        let batch = env.step(&[step % 9, (step / 3) % 9, 0])?;
        for slot in 0..3 {
            let snapshot = env.test_game(slot).snapshot();
            let state = env.slot_state(slot)?;
            assert_eq!(state, SlotState::read(env.test_game(slot)));
            assert_eq!(env.slot_state(slot)?, state);
            assert_eq!(env.test_game(slot).snapshot(), snapshot);
        }
        if batch.terminated.iter().any(|t| *t) {
            break;
        }
    }
    // Slots are different games.
    assert_ne!(env.slot_state(0)?, env.slot_state(1)?);
    assert_eq!(env.slot_state(3).err(), Some(EnvError::SlotIndex(3)));
    Ok(())
}

#[test]
fn an_ended_slot_still_reads() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        raw_frame_cap: 4,
        ..EnvConfig::default()
    })?;
    assert!(env.step(&[0])?.truncated[0]);
    let state = env.slot_state(0)?;
    assert_eq!(state, SlotState::read(env.test_game(0)));
    Ok(())
}
