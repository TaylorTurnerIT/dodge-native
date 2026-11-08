//! Inspect one identity-matched trajectory from the stratified fidelity probe.
use dodge_core::{Action, NativeConfig, NativeGame};
use dodge_danger::{hnnplan, start_game};

fn main() -> Result<(), String> {
    let a: Vec<_> = std::env::args().collect();
    if !(7..=8).contains(&a.len()) {
        return Err(
            "usage: fidelity_inspect MODEL SEED DIFFICULTY FRAME SEQUENCE HORIZON [DRIVER_MODEL]"
                .into(),
        );
    }
    let model = hnnplan::PhysicsModel::from_json(
        &std::fs::read_to_string(&a[1]).map_err(|e| e.to_string())?,
    )?;
    let driver = if a.len() == 8 {
        hnnplan::PhysicsModel::from_json(
            &std::fs::read_to_string(&a[7]).map_err(|e| e.to_string())?,
        )?
    } else {
        model.clone()
    };
    let seed: u32 = a[2].parse().map_err(|_| "seed")?;
    let difficulty: u8 = a[3].parse().map_err(|_| "difficulty")?;
    let frame: u32 = a[4].parse().map_err(|_| "frame")?;
    let seq: usize = a[5].parse().map_err(|_| "sequence")?;
    let horizon: usize = a[6].parse().map_err(|_| "horizon")?;
    if seq >= 29 || horizon > 36 {
        return Err("sequence or horizon out of range".into());
    }
    let mut game = NativeGame::new(NativeConfig {
        seed,
        difficulty,
        patterns_enabled: true,
        powerups_enabled: false,
        ..NativeConfig::new(seed)
    });
    start_game(&mut game)?;
    let mut history = hnnplan::RectSnapshot::new();
    dodge_danger::observe::reset();
    for _ in 0..frame {
        hnnplan::set_history(history.clone());
        dodge_danger::observe::feed(&game);
        let (action, _) = hnnplan::choose(&driver, &game, 36);
        history = hnnplan::rect_snapshot(&game);
        if game
            .advance_frame_headless(action.mask())
            .map_err(|e| e.to_string())?
            .dead
        {
            return Err("game died before target state".into());
        }
    }
    hnnplan::set_history(history);
    dodge_danger::observe::feed(&game);
    let ids: Vec<_> = game
        .enemy_serials()
        .ok_or("no ids")?
        .iter()
        .zip(game.enemies())
        .filter(|(_, e)| e.personality < 2)
        .map(|(id, _)| *id)
        .collect();
    let mut rng = u64::from(seed) ^ (u64::from(frame) << 32) ^ u64::from(difficulty);
    let mut actions = Vec::new();
    for s in 0..=seq {
        actions = (0..36)
            .map(|_| {
                if s < 9 {
                    s
                } else {
                    rng ^= rng << 13;
                    rng ^= rng >> 7;
                    rng ^= rng << 17;
                    (rng % 9) as usize
                }
            })
            .collect();
    }
    let mut sim = game.clone();
    for &index in &actions[..horizon] {
        if sim
            .advance_frame_headless(Action::ALL[index].mask())
            .map_err(|e| e.to_string())?
            .dead
        {
            return Err("engine died before target horizon".into());
        }
    }
    let predicted = hnnplan::imagine_actions_at(&model, &game, &actions, horizon as u32);
    let final_ids = sim.enemy_serials().ok_or("no ids")?;
    let mut worst = None;
    for (body, id) in predicted.snapshot.iter().zip(&predicted.snapshot_ids) {
        if let Some((id, enemy)) = id.and_then(|i| ids.get(i)).and_then(|id| {
            final_ids
                .iter()
                .position(|x| x == id)
                .map(|j| (*id, &sim.enemies()[j]))
        }) {
            let error = (body[0] - enemy.x.to_double()).hypot(body[1] - enemy.y.to_double());
            if worst.as_ref().is_none_or(|(old, _)| error > *old) {
                worst = Some((error, id));
            }
        }
    }
    let (error, id) = worst.ok_or("no matched enemy")?;
    let initial_index = ids.iter().position(|v| *v == id).ok_or("id missing")?;
    println!(
        "max error {error:.4}, initial threat index {initial_index}; initial rectangles {:?}",
        hnnplan::rect_snapshot(&game)
    );
    let mut sim = game.clone();
    for step in 0..=horizon {
        let actual_index = sim
            .enemy_serials()
            .ok_or("no ids")?
            .iter()
            .position(|x| *x == id)
            .ok_or("enemy disappeared")?;
        let e = &sim.enemies()[actual_index];
        if step == 0 {
            println!("initial {:?}", e);
        } else {
            let im = hnnplan::imagine_actions_at(&model, &game, &actions, step as u32);
            let j = im
                .snapshot_ids
                .iter()
                .position(|x| *x == Some(initial_index))
                .ok_or("model enemy disappeared")?;
            println!(
                "{step} engine ({:.3},{:.3}) v ({:.3},{:.3}) size {:.3} dying {} model {:?} rectangles {:?}",
                e.x.to_double(),
                e.y.to_double(),
                e.vx.to_double(),
                e.vy.to_double(),
                e.size.to_double(),
                e.is_dying,
                im.snapshot[j],
                hnnplan::rect_snapshot(&sim)
            );
        }
        if step < horizon {
            sim.advance_frame_headless(Action::ALL[actions[step]].mask())
                .map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}
