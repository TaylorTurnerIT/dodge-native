//! Replay one death and compare the learned model's imagined enemies with the engine's.
//!
//! usage: explain_death MODEL.json SEED DIFFICULTY PATTERNS(0|1) DEATH_FRAME FRAMES_BEFORE_DEATH
//! The game is replayed with the hnn policy to the last savable state. From there the planner's
//! chosen action is held for a few frames, in the engine and in the model, and every enemy that
//! is close to the player is printed with its position error.

use dodge_core::{Action, NativeConfig, NativeGame};
use dodge_danger::{hnnplan, start_game};

fn main() -> Result<(), String> {
    let a: Vec<String> = std::env::args().collect();
    if a.len() < 7 {
        return Err(
            "usage: explain_death MODEL SEED DIFFICULTY PATTERNS DEATH_FRAME BEFORE".into(),
        );
    }
    let model = hnnplan::PhysicsModel::from_json(
        &std::fs::read_to_string(&a[1]).map_err(|e| e.to_string())?,
    )?;
    hnnplan::install(model.clone())?;
    let seed: u32 = a[2].parse().map_err(|_| "seed")?;
    let difficulty: u8 = a[3].parse().map_err(|_| "difficulty")?;
    let patterns = a[4] == "1";
    let death_frame: u32 = a[5].parse().map_err(|_| "death frame")?;
    let before: u32 = a[6].parse().map_err(|_| "before")?;

    let mut game = NativeGame::new(NativeConfig {
        seed,
        difficulty,
        patterns_enabled: patterns,
        powerups_enabled: false,
        ..NativeConfig::new(seed)
    });
    start_game(&mut game)?;
    let stop = death_frame.saturating_sub(before);
    let mut memory = hnnplan::RectSnapshot::new();
    dodge_danger::observe::reset();
    for _ in 0..stop {
        hnnplan::set_history(memory.clone());
        dodge_danger::observe::feed(&game);
        let (action, _) = hnnplan::choose(&model, &game, 36);
        memory = hnnplan::rect_snapshot(&game);
        game.advance_frame_headless(action.mask())
            .map_err(|e| e.to_string())?;
    }
    hnnplan::set_history(memory.clone());
    dodge_danger::observe::feed(&game);
    let (action, costs) = hnnplan::choose(&model, &game, 36);
    let index = Action::ALL.iter().position(|x| *x == action).unwrap_or(0);
    let player = game.player();
    println!(
        "state at frame {stop}: player ({:.1},{:.1}) planner action {} model cost {:.0}; rects {}",
        player.x.to_double(),
        player.y.to_double(),
        action.name(),
        costs[index],
        hnnplan::rect_snapshot(&game).len()
    );
    for (i, r) in hnnplan::rect_snapshot(&game).iter().enumerate() {
        println!(
            "  rect {i}: x {:.1} y {:.1} w {:.1} h {:.1} progress {:.2} moving {}",
            r[0], r[1], r[2], r[3], r[4], r[5]
        );
    }
    println!(
        "  per action (held 36 frames): model cost | model predicts hit at | engine kills at (cause)"
    );
    for (i, act) in Action::ALL.iter().enumerate() {
        let im = hnnplan::imagine(&model, &game, i, 36, 0);
        let mut sim = game.clone();
        let mut killed = None;
        for f in 1..=36_u32 {
            if sim
                .advance_frame_headless(act.mask())
                .map_err(|e| e.to_string())?
                .dead
            {
                killed = Some(f);
                break;
            }
        }
        let cause = if killed.is_some() {
            sim.death_diagnostic()
                .cause()
                .map_or("unknown", |c| c.as_str())
        } else {
            ""
        };
        println!(
            "    {:10} {:8.0} | {:?} | {:?} {}",
            act.name(),
            im.cost,
            im.first_hit,
            killed,
            cause
        );
    }
    for n in [1_u32, 2, 3, 4, 6] {
        let imagined = hnnplan::imagine(&model, &game, index, 36, n);
        let mut sim = game.clone();
        let mut dead = false;
        for _ in 0..n {
            let r = sim
                .advance_frame_headless(action.mask())
                .map_err(|e| e.to_string())?;
            dead |= r.dead;
        }
        let truth: Vec<_> = sim.enemies().iter().filter(|e| e.personality < 2).collect();
        let p = sim.player();
        print!(
            "  +{n} frames{}:",
            if dead { " (engine: DEAD)" } else { "" }
        );
        if truth.len() != imagined.snapshot.len() {
            let extra = truth.last().map_or(String::new(), |t| {
                format!(
                    "newest engine enemy: kind {} at ({:.1},{:.1}) size {:.0}, {:.1} px from the player",
                    t.personality, t.x.to_double(), t.y.to_double(), t.size.to_double(),
                    (t.x.to_double() - p.x.to_double()).hypot(t.y.to_double() - p.y.to_double())
                )
            });
            println!(
                " enemy count differs: engine {} vs model {} | {extra}",
                truth.len(),
                imagined.snapshot.len()
            );
            continue;
        }
        let mut worst = (0.0, 0usize);
        for (i, (t, m)) in truth.iter().zip(&imagined.snapshot).enumerate() {
            let err = (t.x.to_double() - m[0]).hypot(t.y.to_double() - m[1]);
            if err > worst.0 {
                worst = (err, i);
            }
        }
        let t = truth[worst.1];
        println!(
            " worst enemy error {:.2}px: kind {} engine ({:.1},{:.1}) size {:.0} dying {} | its distance to player {:.1}",
            worst.0,
            t.personality,
            t.x.to_double(),
            t.y.to_double(),
            t.size.to_double(),
            t.is_dying,
            (t.x.to_double() - p.x.to_double()).hypot(t.y.to_double() - p.y.to_double())
        );
    }
    if std::env::var("EXPLAIN_DETAIL").is_ok() {
        let mut sim = game.clone();
        for n in 1_u32..=5 {
            let r = sim
                .advance_frame_headless(action.mask())
                .map_err(|e| e.to_string())?;
            let imagined = hnnplan::imagine(&model, &game, index, 36, n);
            let p = sim.player();
            let (px, py) = (p.x.to_double(), p.y.to_double());
            println!(
                "  detail +{n}{} player ({px:.1},{py:.1}) model enemies {} engine enemies {}",
                if r.dead { " DEAD" } else { "" },
                imagined.snapshot.len(),
                sim.enemies().iter().filter(|e| e.personality < 2).count()
            );
            for e in sim.enemies().iter().filter(|e| e.personality < 2) {
                let (ex, ey) = (e.x.to_double(), e.y.to_double());
                if (ex - px).hypot(ey - py) > 22.0 {
                    continue;
                }
                let near = imagined
                    .snapshot
                    .iter()
                    .min_by(|a, b| {
                        (a[0] - ex)
                            .hypot(a[1] - ey)
                            .total_cmp(&(b[0] - ex).hypot(b[1] - ey))
                    })
                    .map_or(String::from("none"), |m| {
                        format!(
                            "model nearest ({:.1},{:.1}) err {:.2}",
                            m[0],
                            m[1],
                            (m[0] - ex).hypot(m[1] - ey)
                        )
                    });
                println!(
                    "     enemy kind {} at ({ex:.1},{ey:.1}) v ({:.2},{:.2}) size {:.0} dying {} | {near}",
                    e.personality,
                    e.vx.to_double(),
                    e.vy.to_double(),
                    e.size.to_double(),
                    e.is_dying
                );
            }
        }
    }
    // Does this replay reach the recorded death?
    let mut frame = stop;
    let mut first = true;
    loop {
        if !first {
            dodge_danger::observe::feed(&game);
        }
        first = false;
        hnnplan::set_history(memory.clone());
        let (action, _) = hnnplan::choose(&model, &game, 36);
        memory = hnnplan::rect_snapshot(&game);
        let result = game
            .advance_frame_headless(action.mask())
            .map_err(|e| e.to_string())?;
        frame += 1;
        if result.dead || frame > death_frame + 3000 {
            println!(
                "replay: dead={} at frame {frame} (recorded death frame {death_frame})",
                result.dead
            );
            break;
        }
    }
    Ok(())
}
