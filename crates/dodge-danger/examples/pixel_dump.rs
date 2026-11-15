//! Generate indexed pixels and engine labels. Run with --help for options.
use dodge_core::{Action, NativeConfig, NativeGame, FRAMEBUFFER_SIZE};
use dodge_danger::{hnnplan, start_game, stream_episode, DangerConfig, PolicyKind};
use serde_json::json;
use std::{collections::VecDeque, fs::{self, File}, io::{BufWriter, Write}, path::PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    if args.iter().any(|x| x == "--help") {
        println!("pixel_dump MODEL OUTPUT [--frames N] [--stride N] [--seed N] [--game-cap N]");
        return Ok(());
    }
    if args.len() < 3 { return Err("expected MODEL OUTPUT; use --help".into()); }
    let opt = |name: &str, default: u32| -> Result<u32, String> {
        match args.iter().position(|a| a == name) {
            Some(i) => args.get(i+1).ok_or_else(|| format!("missing {name}"))?.parse().map_err(|_| format!("invalid {name}")),
            None => Ok(default),
        }
    };
    let total = opt("--frames", 200_000)?;
    let stride = opt("--stride", 4)?;
    let mut seed = opt("--seed", 1)?;
    let cap = opt("--game-cap", 8_000)?;
    if total == 0 || stride == 0 || cap == 0 { return Err("counts must be positive".into()); }
    let output = PathBuf::from(&args[2]);
    fs::create_dir_all(&output)?;
    if fs::read_dir(&output)?.next().is_some() { return Err("output directory must be empty".into()); }
    let model = hnnplan::PhysicsModel::from_json(&fs::read_to_string(&args[1])?)?;
    hnnplan::install(model)?;
    let mut count: u32 = 0;
    let mut shard: Option<(BufWriter<File>, BufWriter<File>)> = None;
    while count < total {
        let game_index = seed.wrapping_sub(opt("--seed", 1)?);
        let difficulty = (game_index % 3 + 1) as u8;
        let patterns = (game_index / 3) % 2 != 0;
        let policy = if (game_index / 6) % 2 == 0 { PolicyKind::Hnn } else { PolicyKind::Lookahead };
        let config = DangerConfig { seed, difficulty, patterns, max_frames: cap, heat_every: u32::MAX, ..Default::default() };
        let mut game = NativeGame::new(NativeConfig { seed, difficulty, patterns_enabled: patterns, powerups_enabled: false, ..NativeConfig::new(seed) });
        start_game(&mut game)?;
        let mut frame = 0_u32;
        let mut history = VecDeque::<u32>::new();
        let mut sink = |record: dodge_danger::FrameRecord| -> Result<(), String> {
            if frame % stride == 0 && count < total {
                if count % 20_000 == 0 {
                    let base = format!("shard-{:05}", count / 20_000);
                    shard = Some((BufWriter::new(File::create(output.join(format!("{base}.bin"))).map_err(|e| e.to_string())?), BufWriter::new(File::create(output.join(format!("{base}.jsonl"))).map_err(|e| e.to_string())?)));
                }
                let (pixels, labels) = shard.as_mut().ok_or("missing shard")?;
                let mut image = [0; FRAMEBUFFER_SIZE];
                game.render_into(&mut image);
                pixels.write_all(&image).map_err(|e| e.to_string())?;
                let v = game.privileged_view();
                let p = v.player;
                let enemies: Vec<_> = v.enemies.iter().map(|e| {
                    let rate = v.speed.to_double() * v.freeze_rate.to_double() * e.speed.to_double();
                    json!({"x":e.x.to_double(),"y":e.y.to_double(),"size":e.size.to_double(),"kind":e.personality,"vx":e.vx.to_double(),"vy":e.vy.to_double(),"rate":rate,"vx_rate":e.vx.to_double()*rate,"vy_rate":e.vy.to_double()*rate,"dying":e.is_dying,"inside":e.inside})
                }).collect();
                let rects: Vec<_> = v.active_pattern.map(|pat| pat.rects.iter().map(|r| json!({"x":r.x.to_double(),"y":r.y.to_double(),"w":r.width.to_double(),"h":r.height.to_double(),"progress":r.sh.to_double(),"moving":pat.pattern_type == 1})).collect()).unwrap_or_default();
                let label = json!({"index":count,"frame":frame,"seed":seed,"difficulty":difficulty,"patterns":patterns,"policy":policy.name(),"stride":stride,"previous":history.iter().copied().collect::<Vec<_>>(),"player":{"x":p.x.to_double(),"y":p.y.to_double(),"vx":p.vx.to_double(),"vy":p.vy.to_double(),"size":p.size.to_double()},"enemies":enemies,"rects":rects,"speed":v.speed.to_double()});
                writeln!(labels,"{label}").map_err(|e| e.to_string())?;
                history.push_front(count); if history.len() > 4 { history.pop_back(); }
                count += 1;
            }
            let action = Action::ALL.iter().copied().find(|a| a.name() == record.a).ok_or("unknown action")?;
            game.advance_frame_headless(action.mask()).map_err(|e| e.to_string())?;
            frame += 1;
            if count >= total { return Err("pixel dump complete".into()); }
            Ok(())
        };
        if let Err(e) = stream_episode(&config, policy, Some(cap), &mut sink) {
            if e != "pixel dump complete" { return Err(e.into()); }
        }
        seed = seed.checked_add(1).ok_or("seed overflow")?;
    }
    if let Some((mut pixels, mut labels)) = shard { pixels.flush()?; labels.flush()?; }
    println!("wrote {count} frames");
    Ok(())
}
