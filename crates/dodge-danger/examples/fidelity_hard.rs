//! Stratified first-hit probe. Usage: fidelity_hard MODEL DEATHS.ndjson
use dodge_core::{Action, NativeConfig, NativeGame};
use dodge_danger::{hnnplan, start_game};
use serde_json::json;
use std::collections::BTreeMap;

fn main() -> Result<(), String> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 {
        return Err("usage: fidelity_hard MODEL DEATHS.ndjson".into());
    }
    let model = hnnplan::PhysicsModel::from_json(
        &std::fs::read_to_string(&args[1]).map_err(|e| e.to_string())?,
    )?;
    let text = std::fs::read_to_string(&args[2]).map_err(|e| e.to_string())?;
    let mut deaths = BTreeMap::new();
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        let row: serde_json::Value = serde_json::from_str(line).map_err(|e| e.to_string())?;
        let seed = row["seed"].as_u64().ok_or("death seed")? as u32;
        let frame = row["death_frame"].as_u64().ok_or("death frame")? as u32;
        if row["difficulty"].as_u64() != Some(3)
            || !(50000..50300).contains(&seed)
            || !(300..=8000).contains(&frame)
            || deaths.insert(seed, frame).is_some()
        {
            return Err("invalid, duplicate, or out-of-range death record".into());
        }
    }
    if deaths.len() < 3 {
        return Err("at least three fresh D3 death cases are required".into());
    }
    let per_death = 800_usize.div_ceil(deaths.len()).min(300) as u32;
    let mut counts = [[0_usize; 4]; 3];
    let mut pre_death = 0_usize;
    let mut total = 0_usize;
    for difficulty in 1..=3 {
        for seed in 50000..50300 {
            let death_frame = (difficulty == 3)
                .then(|| deaths.get(&seed).copied())
                .flatten();
            let index = usize::from(difficulty - 1);
            if counts[index].iter().all(|n| *n >= 100) && death_frame.is_none() {
                continue;
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
            let mut observed_death = None;
            for frame in 0..8000 {
                hnnplan::set_history(history.clone());
                dodge_danger::observe::feed(&game);
                let bin = if frame < 500 {
                    0
                } else if frame < 2000 {
                    1
                } else if frame < 5000 {
                    2
                } else {
                    3
                };
                let pre = death_frame.is_some_and(|d| frame >= d - 300 && frame < d);
                let selected_death = pre && {
                    let offset = frame - (death_frame.unwrap_or(300) - 300);
                    offset * per_death / 300 != (offset + 1) * per_death / 300
                };
                let selected = selected_death || (frame % 25 == 0 && counts[index][bin] < 100);
                if selected {
                    total += 1;
                    if pre {
                        pre_death += 1;
                    }
                    counts[index][bin] += 1;
                    let p = game.player();
                    let (px, py) = (p.x.to_double(), p.y.to_double());
                    let enemies: Vec<_> = game
                        .enemies()
                        .iter()
                        .filter(|e| e.personality < 2)
                        .collect();
                    let near_wall = px.min(py).min(128.0 - px).min(128.0 - py) < 16.0;
                    let rects = hnnplan::rect_snapshot(&game);
                    let near_rect = rects.iter().any(|r| {
                        px >= r[0] - 16.0
                            && px <= r[0] + r[2] + 16.0
                            && py >= r[1] - 16.0
                            && py <= r[1] + r[3] + 16.0
                    });
                    let contact = enemies.iter().enumerate().any(|(i, a)| {
                        enemies.iter().skip(i + 1).any(|b| {
                            (a.x.to_double() - b.x.to_double())
                                .hypot(a.y.to_double() - b.y.to_double())
                                < 8.0
                        })
                    });
                    let kamikaze = enemies.iter().any(|e| {
                        e.personality == 1
                            && (e.x.to_double() - px).hypot(e.y.to_double() - py) < 25.0
                    });
                    let initial_serials: Vec<_> = game
                        .enemy_serials()
                        .ok_or("enemy identity unavailable")?
                        .iter()
                        .zip(game.enemies())
                        .filter(|(_, e)| e.personality < 2)
                        .map(|(serial, _)| *serial)
                        .collect();
                    let mut rng =
                        u64::from(seed) ^ (u64::from(frame) << 32) ^ u64::from(difficulty);
                    for seq in 0..29 {
                        let actions: Vec<usize> = (0..36)
                            .map(|_| {
                                if seq < 9 {
                                    seq
                                } else {
                                    rng ^= rng << 13;
                                    rng ^= rng >> 7;
                                    rng ^= rng << 17;
                                    (rng % 9) as usize
                                }
                            })
                            .collect();
                        let predicted = hnnplan::imagine_actions(&model, &game, &actions).first_hit;
                        let mut sim = game.clone();
                        let mut actual = None;
                        let mut snapshots = Vec::new();
                        for (n, index) in actions.iter().enumerate() {
                            if sim
                                .advance_frame_headless(Action::ALL[*index].mask())
                                .map_err(|e| e.to_string())?
                                .dead
                            {
                                actual = Some(n + 1);
                                break;
                            }
                            let horizon = (n + 1) as u32;
                            if ![4, 8, 12, 24, 36].contains(&horizon)
                                || predicted.is_some_and(|hit| hit <= horizon)
                            {
                                continue;
                            }
                            let imagined =
                                hnnplan::imagine_actions_at(&model, &game, &actions, horizon);
                            let serials =
                                sim.enemy_serials().ok_or("enemy identity unavailable")?;
                            let truth: BTreeMap<_, _> = serials
                                .iter()
                                .zip(sim.enemies())
                                .filter(|(_, enemy)| enemy.personality < 2)
                                .map(|(serial, enemy)| (*serial, enemy))
                                .collect();
                            let mut position_errors = Vec::new();
                            let mut explosion_size_errors = Vec::new();
                            for (body, id) in imagined.snapshot.iter().zip(&imagined.snapshot_ids) {
                                let Some(enemy) = id
                                    .and_then(|id| initial_serials.get(id))
                                    .and_then(|id| truth.get(id))
                                else {
                                    continue;
                                };
                                position_errors.push(
                                    (body[0] - enemy.x.to_double())
                                        .hypot(body[1] - enemy.y.to_double()),
                                );
                                if enemy.personality == -1 {
                                    explosion_size_errors
                                        .push((body[2] - enemy.size.to_double()).abs());
                                }
                            }
                            let initial_survivors = initial_serials
                                .iter()
                                .filter(|id| truth.contains_key(id))
                                .count();
                            snapshots.push(json!({"horizon": horizon, "engine_count": truth.len(), "model_count": imagined.snapshot.len(),
                                "engine_new": truth.len() - initial_survivors, "engine_missing_initial": initial_serials.len() - initial_survivors,
                                "model_new": imagined.snapshot_ids.iter().filter(|id| id.is_none()).count(),
                                "position_errors": position_errors, "explosion_size_errors": explosion_size_errors}));
                        }
                        println!(
                            "{}",
                            json!({"seed": seed, "difficulty": difficulty, "frame": frame, "sequence": seq, "engine_hit": actual, "model_hit": predicted, "near_wall": near_wall, "near_rectangle": near_rect, "enemy_contact": contact, "kamikaze_near": kamikaze, "pre_death": pre, "speed": game.privileged_view().speed.to_double(), "snapshots": snapshots})
                        );
                    }
                }
                let (action, _) = hnnplan::choose(&model, &game, 36);
                history = hnnplan::rect_snapshot(&game);
                if game
                    .advance_frame_headless(action.mask())
                    .map_err(|e| e.to_string())?
                    .dead
                {
                    observed_death = Some(game.survival_frames());
                    break;
                }
            }
            if let Some(expected) = death_frame {
                if observed_death != Some(expected) {
                    return Err(format!(
                        "death replay mismatch for seed {seed}: expected {expected}, got {observed_death:?}"
                    ));
                }
            }
        }
    }
    eprintln!("states={total} pre_death={pre_death} strata={counts:?}");
    if counts.iter().flatten().any(|n| *n < 100) || pre_death * 5 < total * 2 {
        return Err("sample does not meet the requested strata or pre-death fraction".into());
    }
    Ok(())
}
