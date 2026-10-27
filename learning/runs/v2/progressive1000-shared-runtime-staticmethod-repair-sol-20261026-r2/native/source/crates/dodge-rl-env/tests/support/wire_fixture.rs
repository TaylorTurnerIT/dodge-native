//! Validation-only snapshot edits. Production has no restore/snapshot path.
//! Pinned v1 wire offsets are checked against decoded fields before and after.
use dodge_core::{EnemyState, NativeGame, Snapshot};

pub fn with_enemies(game: &NativeGame, enemies: &[EnemyState]) -> crate::Result<Snapshot> {
    let snapshot = game.snapshot();
    let state = snapshot.logical_state();
    let mut bytes = snapshot.canonical_bytes();
    // magic/version/schema/cartridge = 44; seed = 4; lifecycle = 10;
    // input = 3; rng = 4 + 4*degree + 2; player = 20.
    let start = 44 + 4 + 10 + 3 + 4 + 4 * state.rng.state.len() + 2 + 20;
    assert_eq!(
        u32::from_le_bytes(bytes[start..start + 4].try_into()?) as usize,
        state.enemies.len()
    );
    let old_length = 4 + state
        .enemies
        .iter()
        .map(|e| 33 + if e.life.is_some() { 4 } else { 0 })
        .sum::<usize>();
    let mut replacement = Vec::new();
    replacement.extend(u32::try_from(enemies.len())?.to_le_bytes());
    for e in enemies {
        for v in [e.x, e.y, e.vx, e.vy, e.size, e.max_size] {
            replacement.extend(v.raw().to_le_bytes());
        }
        replacement.push(e.personality as u8);
        replacement.extend(e.speed.raw().to_le_bytes());
        replacement.extend([
            u8::from(e.inside),
            u8::from(e.is_dying),
            u8::from(e.isizing),
            u8::from(e.life.is_some()),
        ]);
        if let Some(life) = e.life {
            replacement.extend(life.raw().to_le_bytes());
        }
    }
    bytes.splice(start..start + old_length, replacement);
    let result = Snapshot::from_canonical_bytes(&bytes)?;
    let mut expected = state.clone();
    expected.enemies = enemies.to_vec();
    assert_eq!(result.logical_state(), &expected);
    assert_eq!(result.render_state(), snapshot.render_state());
    assert_eq!(result.framebuffer(), snapshot.framebuffer());
    Ok(result)
}

fn pattern_bytes(p: &dodge_core::PatternState) -> Vec<u8> {
    use dodge_core::PatternTarget;
    let mut b = Vec::new();
    b.push(p.id);
    for v in [p.mins, p.maxs, p.probability] {
        b.extend(v.raw().to_le_bytes());
    }
    b.extend((p.variants.len() as u32).to_le_bytes());
    b.extend(&p.variants);
    b.extend([
        u8::from(p.smooth),
        p.pattern_type,
        u8::from(p.bounce_cap),
        u8::from(p.spawn_enabled),
        u8::from(p.automatic_variant.is_some()),
    ]);
    if let Some(v) = p.automatic_variant {
        b.push(v);
    }
    b.extend(p.special.raw().to_le_bytes());
    b.extend(p.counter.to_le_bytes());
    b.extend(p.timer.raw().to_le_bytes());
    b.extend((p.rects.len() as u32).to_le_bytes());
    for r in &p.rects {
        for v in [r.x, r.y, r.width, r.height, r.speed, r.dx, r.dy] {
            b.extend(v.raw().to_le_bytes());
        }
        b.extend((r.targets.len() as u32).to_le_bytes());
        for t in &r.targets {
            match t {
                PatternTarget::Move {
                    x,
                    y,
                    width,
                    height,
                } => {
                    b.push(0);
                    for v in [x, y, width, height] {
                        b.extend(v.raw().to_le_bytes());
                    }
                }
                PatternTarget::Wait(v) => {
                    b.push(1);
                    b.extend(v.raw().to_le_bytes());
                }
                PatternTarget::SetFyou(v) => b.extend([2, u8::from(*v)]),
                PatternTarget::SetSpawns(points) => {
                    b.push(3);
                    b.extend((points.len() as u32).to_le_bytes());
                    for p in points {
                        b.extend(p.x.raw().to_le_bytes());
                        b.extend(p.y.raw().to_le_bytes());
                    }
                }
            }
        }
        b.extend((r.target_index as u32).to_le_bytes());
        b.extend(r.wait.raw().to_le_bytes());
        b.push(u8::from(r.shown));
        b.extend(r.sh.raw().to_le_bytes());
        b.extend((r.warnings.len() as u32).to_le_bytes());
        for w in &r.warnings {
            for v in [w.x0, w.y0, w.x1, w.y1] {
                b.extend(v.raw().to_le_bytes());
            }
        }
        b.extend([u8::from(r.collision_done), u8::from(r.finished)]);
    }
    b
}

/// Synthetic safety fixture only: remove spawn points without changing clocks,
/// RNG, player, enemies, settings or any other decoded native state. Used with
/// patterns/powerups disabled to exercise long raw-frame boundaries safely.
pub fn without_spawns(game: &NativeGame) -> crate::Result<Snapshot> {
    let snapshot = game.snapshot();
    let state = snapshot.logical_state();
    let mut bytes = snapshot.canonical_bytes();
    let start = 44
        + 4
        + 10
        + 3
        + 4
        + 4 * state.rng.state.len()
        + 2
        + 20
        + 4
        + state
            .enemies
            .iter()
            .map(|e| 33 + if e.life.is_some() { 4 } else { 0 })
            .sum::<usize>()
        + 4
        + 34 * state.particles.len()
        + 4
        + state
            .patterns
            .iter()
            .map(|p| pattern_bytes(p).len())
            .sum::<usize>()
        + if state.active_pattern.is_some() { 5 } else { 1 };
    assert_eq!(
        u32::from_le_bytes(bytes[start..start + 4].try_into()?) as usize,
        state.spawns.len()
    );
    for (i, point) in state.spawns.iter().enumerate() {
        let offset = start + 4 + i * 8;
        assert_eq!(&bytes[offset..offset + 4], &point.x.raw().to_le_bytes());
        assert_eq!(&bytes[offset + 4..offset + 8], &point.y.raw().to_le_bytes());
    }
    bytes.splice(
        start..start + 4 + state.spawns.len() * 8,
        0_u32.to_le_bytes(),
    );
    let result = Snapshot::from_canonical_bytes(&bytes)?;
    let mut expected = state.clone();
    expected.spawns.clear();
    assert_eq!(result.logical_state(), &expected);
    assert_eq!(result.render_state(), snapshot.render_state());
    assert_eq!(result.framebuffer(), snapshot.framebuffer());
    Ok(result)
}

pub fn with_pattern(
    game: &NativeGame,
    pattern: dodge_core::PatternState,
) -> crate::Result<Snapshot> {
    let snapshot = game.snapshot();
    let state = snapshot.logical_state();
    let mut bytes = snapshot.canonical_bytes();
    let enemy_start = 44 + 4 + 10 + 3 + 4 + 4 * state.rng.state.len() + 2 + 20;
    let start = enemy_start
        + 4
        + state
            .enemies
            .iter()
            .map(|e| 33 + if e.life.is_some() { 4 } else { 0 })
            .sum::<usize>()
        + 4
        + 34 * state.particles.len();
    assert_eq!(
        u32::from_le_bytes(bytes[start..start + 4].try_into()?) as usize,
        state.patterns.len()
    );
    let old = state
        .patterns
        .iter()
        .flat_map(pattern_bytes)
        .collect::<Vec<_>>();
    assert_eq!(&bytes[start + 4..start + 4 + old.len()], &old);
    let mut new = 1_u32.to_le_bytes().to_vec();
    new.extend(pattern_bytes(&pattern));
    new.push(1);
    new.extend(0_u32.to_le_bytes());
    let old_active = if state.active_pattern.is_some() { 5 } else { 1 };
    bytes.splice(start..start + 4 + old.len() + old_active, new);
    let result = Snapshot::from_canonical_bytes(&bytes)?;
    let mut expected = state.clone();
    expected.patterns = vec![pattern];
    expected.active_pattern = Some(0);
    assert_eq!(result.logical_state(), &expected);
    Ok(result)
}
