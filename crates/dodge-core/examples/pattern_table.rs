//! Print the static pattern table as JSON: id, type, score gate, variants, size.
//!
//! Run with `cargo run -p dodge-core --example pattern_table`. Patterns are
//! identified by `PatternState.id`; a "variant" is a sibling id (mirror or
//! transpose) listed in `variants`, so a family is the connected id set.
use dodge_core::{CoreError, NativeConfig, NativeGame};

fn main() -> Result<(), CoreError> {
    let game = NativeGame::new(NativeConfig::new(42));
    let rows = game
        .patterns()
        .iter()
        .map(|pattern| {
            let variants = pattern
                .variants
                .iter()
                .map(u8::to_string)
                .collect::<Vec<_>>()
                .join(",");
            format!(
                "  {{\"id\":{},\"pattern_type\":{},\"mins\":{},\"maxs\":{},\"variants\":[{}],\"rects\":{},\"smooth\":{},\"spawn_enabled\":{},\"automatic_variant\":{}}}",
                pattern.id,
                pattern.pattern_type,
                pattern.mins.to_double(),
                pattern.maxs.to_double(),
                variants,
                pattern.rects.len(),
                pattern.smooth,
                pattern.spawn_enabled,
                pattern
                    .automatic_variant
                    .map_or_else(|| "null".to_owned(), |v| v.to_string()),
            )
        })
        .collect::<Vec<_>>();
    println!("[\n{}\n]", rows.join(",\n"));
    Ok(())
}
