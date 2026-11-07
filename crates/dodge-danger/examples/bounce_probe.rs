//! Record the post-bounce speed of enemies against lethal pattern rectangles over a whole game.
//! Observation only: positions and velocities of consecutive frames, no engine constants.
//! usage: bounce_probe MODEL.json DIFFICULTY FIRST_SEED SEEDS FRAMES
//! Prints: difficulty frame moving(0|1) axis(x|y) post_speed other_axis_changed(0|1)

use dodge_core::{NativeConfig, NativeGame};
use dodge_danger::{hnnplan, start_game};

const FRICTION: f64 = 64880.0 / 65536.0;

fn main() -> Result<(), String> {
    let a: Vec<String> = std::env::args().collect();
    let model = hnnplan::PhysicsModel::from_json(
        &std::fs::read_to_string(&a[1]).map_err(|e| e.to_string())?,
    )?;
    hnnplan::install(model.clone())?;
    let difficulty: u8 = a[2].parse().map_err(|_| "difficulty")?;
    let first: u32 = a[3].parse().map_err(|_| "seed")?;
    let seeds: u32 = a[4].parse().map_err(|_| "seeds")?;
    let frames: u32 = a[5].parse().map_err(|_| "frames")?;
    for seed in first..first + seeds {
        let mut game = NativeGame::new(NativeConfig {
            seed,
            difficulty,
            patterns_enabled: true,
            powerups_enabled: false,
            ..NativeConfig::new(seed)
        });
        start_game(&mut game)?;
        let mut memory = hnnplan::RectSnapshot::new();
        for frame in 0..frames {
            hnnplan::set_history(memory.clone());
            let (action, _) = hnnplan::choose(&model, &game, 36);
            memory = hnnplan::rect_snapshot(&game);
            let rects = memory.clone();
            let before: Vec<[f64; 7]> = game
                .enemies()
                .iter()
                .map(|e| {
                    [
                        e.x.to_double(),
                        e.y.to_double(),
                        e.vx.to_double(),
                        e.vy.to_double(),
                        e.size.to_double(),
                        f64::from(e.personality),
                        0.0,
                    ]
                })
                .collect();
            let speed = game.privileged_view().speed.to_double();
            let r = game
                .advance_frame_headless(action.mask())
                .map_err(|e| e.to_string())?;
            if r.dead {
                break;
            }
            let after: Vec<[f64; 6]> = game
                .enemies()
                .iter()
                .map(|e| {
                    [
                        e.x.to_double(),
                        e.y.to_double(),
                        e.vx.to_double(),
                        e.vy.to_double(),
                        e.size.to_double(),
                        f64::from(e.personality),
                    ]
                })
                .collect();
            for rect in &rects {
                // lethal rectangles only: moving ones, or fully warmed-up static ones
                if rect[5] < 0.5 && rect[4] < 1.999 {
                    continue;
                }
                let (x, y, w, h) = (rect[0], rect[1], rect[2], rect[3]);
                for e in &before {
                    if e[5] < 0.0 || e[5] > 1.0 {
                        continue;
                    }
                    let (vx, vy) = (e[2] * FRICTION, e[3] * FRICTION);
                    if !(e[0] + vx < x + w && e[0] + e[4] > x && e[1] + e[4] > y && e[1] + vy < y + h)
                    {
                        continue;
                    }
                    let Some(n) = after.iter().find(|n| {
                        n[5] == e[5]
                            && (n[0] - e[0]).abs() < 8.0
                            && (n[1] - e[1]).abs() < 8.0
                    }) else {
                        continue;
                    };
                    let cx = (n[2] - vx).abs() > 0.05;
                    let cy = (n[3] - vy).abs() > 0.05;
                    if cx {
                        println!("{difficulty} {frame} {} x {:.4} {} {:.4}", rect[5] as u8, n[2].abs(), u8::from(cy), speed);
                    }
                    if cy {
                        println!("{difficulty} {frame} {} y {:.4} {} {:.4}", rect[5] as u8, n[3].abs(), u8::from(cx), speed);
                    }
                }
            }
        }
    }
    Ok(())
}
