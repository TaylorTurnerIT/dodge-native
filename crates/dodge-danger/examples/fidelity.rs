//! First-hit fidelity probe. Emits one JSON row per state and action sequence.
//! Usage: fidelity MODEL SEEDS FRAMES [FIRST_SEED]
use dodge_core::{Action, NativeConfig, NativeGame};
use dodge_danger::{hnnplan, start_game};
use serde_json::json;

fn main() -> Result<(), String> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() < 4 {
        return Err("usage: fidelity MODEL SEEDS FRAMES [FIRST_SEED]".into());
    }
    let model = hnnplan::PhysicsModel::from_json(
        &std::fs::read_to_string(&args[1]).map_err(|e| e.to_string())?,
    )?;
    let seeds: u32 = args[2].parse().map_err(|_| "seeds")?;
    let frames: u32 = args[3].parse().map_err(|_| "frames")?;
    let first: u32 = args
        .get(4)
        .map_or(Ok(50000), |s| s.parse())
        .map_err(|_| "first seed")?;
    for difficulty in 1..=3 {
        for seed in first..first + seeds {
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
            for frame in 0..frames {
                hnnplan::set_history(history.clone());
                dodge_danger::observe::feed(&game);
                if frame % 25 == 0 {
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
                        for (n, index) in actions.iter().enumerate() {
                            if sim
                                .advance_frame_headless(Action::ALL[*index].mask())
                                .map_err(|e| e.to_string())?
                                .dead
                            {
                                actual = Some(n + 1);
                                break;
                            }
                        }
                        println!(
                            "{}",
                            json!({"seed": seed, "difficulty": difficulty, "frame": frame, "sequence": seq, "engine_hit": actual, "model_hit": predicted, "near_wall": near_wall, "near_rectangle": near_rect, "enemy_contact": contact, "kamikaze_near": kamikaze})
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
                    break;
                }
            }
        }
    }
    Ok(())
}
