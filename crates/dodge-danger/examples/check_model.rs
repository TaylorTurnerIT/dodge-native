//! Print the learned model's action for every frame of an NDJSON training set.
//! Used to check that Rust and PyTorch agree: `check_model MODEL.json DATA.ndjson [LIMIT]`.

use dodge_danger::learned::{Model, Observation};
use std::io::BufRead;

fn main() -> Result<(), String> {
    let arguments: Vec<String> = std::env::args().collect();
    let model_path = arguments
        .get(1)
        .ok_or("usage: check_model MODEL DATA [LIMIT]")?;
    let data_path = arguments
        .get(2)
        .ok_or("usage: check_model MODEL DATA [LIMIT]")?;
    let limit: usize = arguments
        .get(3)
        .and_then(|v| v.parse().ok())
        .unwrap_or(usize::MAX);
    let model = Model::from_json(&std::fs::read_to_string(model_path).map_err(|e| e.to_string())?)?;
    let file = std::fs::File::open(data_path).map_err(|e| e.to_string())?;
    let mut done = 0;
    for line in std::io::BufReader::new(file).lines() {
        let line = line.map_err(|e| e.to_string())?;
        let row: serde_json::Value = serde_json::from_str(&line).map_err(|e| e.to_string())?;
        if row.get("end").is_some() {
            continue;
        }
        let numbers = |value: &serde_json::Value| -> Vec<f64> {
            value
                .as_array()
                .map(|a| a.iter().filter_map(|v| v.as_f64()).collect())
                .unwrap_or_default()
        };
        let player: [f64; 5] = numbers(&row["p"]).try_into().map_err(|_| "bad p")?;
        let enemies = row["e"]
            .as_array()
            .map(|a| {
                a.iter()
                    .map(|e| numbers(e).try_into().unwrap_or([0.0; 6]))
                    .collect()
            })
            .unwrap_or_default();
        let rects = row
            .get("r")
            .and_then(|r| r.as_array())
            .map(|a| {
                a.iter()
                    .map(|e| numbers(e).try_into().unwrap_or([0.0; 5]))
                    .collect()
            })
            .unwrap_or_default();
        let view = Observation {
            player,
            enemies,
            rects,
        };
        println!("{}", model.choose(&view).0.name());
        done += 1;
        if done >= limit {
            break;
        }
    }
    Ok(())
}
