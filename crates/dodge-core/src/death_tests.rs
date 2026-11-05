use super::*;
use crate::{DeathCause, PatternRect, Snapshot};

fn running() -> Result<NativeGame, CoreError> {
    let mut game = NativeGame::new(NativeConfig::new(42));
    game.advance_frame_headless(crate::BUTTON_X_MASK)?;
    for _ in 1..13 {
        game.advance_frame_headless(0)?;
    }
    assert_eq!(game.lifecycle.mode, Mode::Game);
    game.friendly_enabled = false;
    game.patterns_enabled = false;
    game.enemy_timer = PicoFixed::from_int(-10_000);
    game.enemies.clear();
    Ok(game)
}

fn enemy_at(personality: i8, x: i32, y: i32) -> EnemyState {
    EnemyState {
        personality,
        ..EnemyState::normal(
            PicoFixed::from_int(x),
            PicoFixed::from_int(y),
            PicoFixed::from_int(3),
        )
    }
}

fn install_rect(game: &mut NativeGame, pattern_type: u8, sh: i32) -> Result<(), CoreError> {
    game.patterns_enabled = true;
    game.active_pattern = Some(0);
    game.pattern_active = true;
    let pattern = game
        .patterns
        .first_mut()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    pattern.pattern_type = pattern_type;
    pattern.rects.truncate(1);
    let rect: &mut PatternRect = pattern
        .rects
        .first_mut()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    rect.x = PicoFixed::from_int(56);
    rect.y = PicoFixed::from_int(56);
    rect.width = PicoFixed::from_int(16);
    rect.height = PicoFixed::from_int(16);
    rect.sh = PicoFixed::from_int(sh);
    rect.dx = PicoFixed::ZERO;
    rect.dy = PicoFixed::ZERO;
    Ok(())
}

fn counts(game: &NativeGame) -> [u16; 6] {
    game.death_diagnostic().observed_contacts()
}

#[test]
fn each_enemy_cause_is_classified_at_the_lethal_contact() -> Result<(), CoreError> {
    for (personality, expected, slot) in [
        (0, DeathCause::NormalEnemy, 0),
        (1, DeathCause::KamikazeEnemy, 1),
        (-1, DeathCause::KamikazeExplosion, 2),
    ] {
        let mut game = running()?;
        assert_eq!(game.death_diagnostic().cause(), None);
        game.enemies.push(enemy_at(personality, 61, 64));
        let result = game.advance_frame_headless(0)?;
        assert!(result.dead);
        assert_eq!(game.death_diagnostic().cause(), Some(expected));
        let mut want = [0u16; 6];
        if let Some(count) = want.get_mut(slot) {
            *count = 1;
        }
        assert_eq!(counts(&game), want);
        // The enemy is removed on contact, so the cause cannot be recovered
        // from entity counts after the fact.
        assert!(game.enemies().is_empty());
    }
    Ok(())
}

#[test]
fn unknown_enemy_personality_is_unknown_but_still_lethal() -> Result<(), CoreError> {
    let mut game = running()?;
    game.enemies.push(enemy_at(-2, 61, 64));
    assert!(game.advance_frame_headless(0)?.dead);
    assert_eq!(game.death_diagnostic().cause(), Some(DeathCause::Unknown));
    Ok(())
}

#[test]
fn pattern_causes_split_static_and_moving() -> Result<(), CoreError> {
    let mut moving = running()?;
    install_rect(&mut moving, 1, 0)?;
    assert!(moving.advance_frame_headless(0)?.dead);
    assert_eq!(
        moving.death_diagnostic().cause(),
        Some(DeathCause::MovingPatternRect)
    );

    let mut charging = running()?;
    install_rect(&mut charging, 0, 0)?;
    assert!(!charging.advance_frame_headless(0)?.dead);
    assert_eq!(charging.death_diagnostic().cause(), None);
    assert_eq!(counts(&charging), [0; 6]);

    let mut full = running()?;
    install_rect(&mut full, 0, 2)?;
    assert!(full.advance_frame_headless(0)?.dead);
    assert_eq!(
        full.death_diagnostic().cause(),
        Some(DeathCause::StaticPatternRect)
    );
    assert_eq!(counts(&full), [0, 0, 0, 1, 0, 0]);
    Ok(())
}

#[test]
fn same_frame_contacts_keep_first_cause_and_label_the_rest_observed() -> Result<(), CoreError> {
    let mut game = running()?;
    game.enemies.push(enemy_at(1, 61, 64));
    game.enemies.push(enemy_at(0, 61, 64));
    game.enemies.push(enemy_at(0, 62, 64));
    game.enemies.push(enemy_at(-1, 61, 64));
    install_rect(&mut game, 1, 0)?;
    let result = game.advance_frame_headless(0)?;
    assert!(result.dead && result.done);
    assert_eq!(
        game.death_diagnostic().cause(),
        Some(DeathCause::KamikazeEnemy),
        "first source-order contact"
    );
    assert_eq!(counts(&game), [2, 1, 1, 0, 1, 0]);
    assert!(game.enemies().is_empty());

    // Order reversed: enemy list order decides, not kind priority.
    let mut game = running()?;
    game.enemies.push(enemy_at(-1, 61, 64));
    game.enemies.push(enemy_at(1, 61, 64));
    assert!(game.advance_frame_headless(0)?.dead);
    assert_eq!(
        game.death_diagnostic().cause(),
        Some(DeathCause::KamikazeExplosion)
    );
    assert_eq!(counts(&game), [0, 1, 1, 0, 0, 0]);

    // Enemies precede pattern rectangles in the legacy loop.
    let mut game = running()?;
    game.enemies.push(enemy_at(0, 61, 64));
    install_rect(&mut game, 0, 2)?;
    assert!(game.advance_frame_headless(0)?.dead);
    assert_eq!(
        game.death_diagnostic().cause(),
        Some(DeathCause::NormalEnemy)
    );
    assert_eq!(counts(&game), [1, 0, 0, 1, 0, 0]);
    Ok(())
}

#[test]
fn cause_is_stable_after_death_and_cleared_by_restart_and_reset() -> Result<(), CoreError> {
    let mut game = running()?;
    game.enemies.push(enemy_at(0, 61, 64));
    assert!(game.advance_frame_headless(0)?.dead);
    let first = game.death_diagnostic();
    // Later dead frames never re-enter collision, so the record is frozen,
    // even if another lethal object appears.
    game.enemies.push(enemy_at(1, 61, 64));
    for _ in 0..3 {
        game.advance_frame_headless(0)?;
        assert_eq!(game.death_diagnostic().cause(), first.cause());
        assert_eq!(
            game.death_diagnostic().observed_contacts(),
            first.observed_contacts()
        );
    }
    // Restart via the X button starts new gameplay with no stale cause.
    game.can_click = true;
    game.advance_frame_headless(crate::BUTTON_X_MASK)?;
    assert!(!game.lifecycle.dead);
    assert_eq!(game.death_diagnostic().cause(), None);
    assert_eq!(counts(&game), [0; 6]);

    let mut game = running()?;
    game.enemies.push(enemy_at(0, 61, 64));
    assert!(game.advance_frame_headless(0)?.dead);
    game.reset();
    assert_eq!(game.death_diagnostic().cause(), None);
    assert_eq!(counts(&game), [0; 6]);
    Ok(())
}

#[test]
fn restore_is_unknown_when_dead_and_empty_when_alive() -> Result<(), CoreError> {
    let mut game = running()?;
    let alive = NativeGame::restore(&game.snapshot())?;
    assert_eq!(alive.death_diagnostic().cause(), None);

    game.enemies.push(enemy_at(0, 61, 64));
    assert!(game.advance_frame_headless(0)?.dead);
    assert_eq!(
        game.death_diagnostic().cause(),
        Some(DeathCause::NormalEnemy)
    );
    let restored = NativeGame::restore(&game.snapshot())?;
    assert_eq!(
        restored.death_diagnostic().cause(),
        Some(DeathCause::Unknown)
    );
    assert_eq!(counts(&restored), [0; 6]);
    let via_bytes = NativeGame::restore_bytes(&game.snapshot().canonical_bytes())?;
    assert_eq!(
        via_bytes.death_diagnostic().cause(),
        Some(DeathCause::Unknown)
    );

    // Restoring over a game with a stale cause installs a fresh value.
    let again = NativeGame::restore(&Snapshot::from_canonical_bytes(
        &running()?.snapshot().canonical_bytes(),
    )?)?;
    assert_eq!(again.death_diagnostic().cause(), None);
    Ok(())
}

#[test]
fn diagnostic_is_invisible_to_snapshot_state_equality_and_rng() -> Result<(), CoreError> {
    let mut game = running()?;
    game.enemies.push(enemy_at(0, 61, 64));
    game.enemies.push(enemy_at(1, 61, 64));
    assert!(game.advance_frame_headless(0)?.dead);
    let mut cleared = game.clone();
    cleared.death = crate::DeathDiagnostic::default();
    assert_eq!(game, cleared);
    assert_eq!(game.full_state(), cleared.full_state());
    assert_eq!(
        game.snapshot().canonical_bytes(),
        cleared.snapshot().canonical_bytes()
    );
    assert_eq!(game.rng_checkpoint(), cleared.rng_checkpoint());
    // The restored (Unknown) twin is also state-identical.
    let restored = NativeGame::restore(&game.snapshot())?;
    assert_eq!(restored.full_state(), game.full_state());
    Ok(())
}

#[test]
fn headless_and_full_paths_agree_on_cause_state_and_rng() -> Result<(), CoreError> {
    for (personality, pattern) in [
        (0, None),
        (1, None),
        (-1, None),
        (0, Some((0, 2))),
        (0, Some((1, 0))),
    ] {
        let mut full = running()?;
        match pattern {
            None => full.enemies.push(enemy_at(personality, 61, 64)),
            Some((kind, sh)) => install_rect(&mut full, kind, sh)?,
        }
        let mut headless = full.clone();
        let rendered = full.advance_frame(0)?;
        let result = headless.advance_frame_headless(0)?;
        assert!(rendered.done && result.done);
        assert_eq!(
            full.death_diagnostic().cause(),
            headless.death_diagnostic().cause()
        );
        assert_eq!(counts(&full), counts(&headless));
        assert_eq!(full.rng_checkpoint(), headless.rng_checkpoint());
        let mut lhs = full.full_state();
        let mut rhs = headless.full_state();
        lhs.physical_screen = rhs.physical_screen.clone();
        rhs.physical_screen = lhs.physical_screen.clone();
        assert_eq!(lhs, rhs);
    }
    Ok(())
}
