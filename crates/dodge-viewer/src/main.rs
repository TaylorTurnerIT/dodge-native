use std::{env, path::PathBuf, process};

use dodge_core::{BUTTON_X_MASK, Button, NativeConfig, NativeGame};
use dodge_viewer::{
    PresentedFrame, ViewerError, integer_viewport, load_trace, present_trace_frame, write_capture,
};
use macroquad::{
    color::{BLACK, Color, WHITE},
    prelude::{
        Conf, DrawTextureParams, FilterMode, KeyCode, Texture2D, clear_background, draw_line,
        draw_rectangle, draw_text, draw_texture_ex, get_frame_time, is_key_down, is_key_pressed,
        next_frame, screen_height, screen_width, vec2,
    },
};

const DEFAULT_WINDOW_SIZE: i32 = 768;
const FRAME_CADENCE_SECONDS: f32 = 1.0 / 60.0;

struct Options {
    trace: Option<PathBuf>,
    frame: usize,
    capture: Option<PathBuf>,
    debug: bool,
    pause: bool,
    seed: u32,
    auto_dodge: bool,
    danger_model: PathBuf,
}

#[macroquad::main(window_conf)]
async fn main() {
    if let Err(error) = run().await {
        eprintln!("dodge-viewer: {error}");
        process::exit(2);
    }
}

fn window_conf() -> Conf {
    Conf {
        window_title: "Dodge Native Viewer".to_owned(),
        window_width: DEFAULT_WINDOW_SIZE,
        window_height: DEFAULT_WINDOW_SIZE,
        high_dpi: true,
        sample_count: 0,
        ..Default::default()
    }
}

async fn run() -> Result<(), ViewerError> {
    let options = parse_options(env::args().skip(1))?;
    let mut model = if options.auto_dodge {
        Some(load_danger_model(&options.danger_model)?)
    } else {
        None
    };
    let trace = options.trace.as_deref().map(load_trace).transpose()?;
    let mut live_game = trace
        .is_none()
        .then(|| NativeGame::new(NativeConfig::new(options.seed)));
    let initial_frame = if let Some(trace) = trace.as_ref() {
        present_trace_frame(trace, options.frame)?
    } else {
        let Some(game) = live_game.as_mut() else {
            return Err(ViewerError::InvalidTrace(
                "live viewer game was not initialized".to_owned(),
            ));
        };
        let result = game
            .advance_frame(BUTTON_X_MASK)
            .map_err(|error| ViewerError::InvalidTrace(error.to_string()))?;
        PresentedFrame::from_snapshot(result.snapshot)?
    };
    if let Some(path) = options.capture.as_deref() {
        write_capture(path, &initial_frame)?;
    }

    let mut frame_index = options.frame;
    let mut elapsed = 0.0_f32;
    let mut show_overlay = false;
    let mut rect_memory = dodge_danger::hnnplan::RectSnapshot::new();
    let mut planner_observed_current = false;
    let mut game_dead = false;
    if options.auto_dodge {
        dodge_danger::observe::reset();
    }
    loop {
        let mut selected_action = dodge_core::Action::Neutral;
        let frame = if let Some(trace) = trace.as_ref() {
            present_trace_frame(trace, frame_index.min(trace.frames.len() - 1))?
        } else {
            let Some(game) = live_game.as_mut() else {
                return Err(ViewerError::InvalidTrace(
                    "live viewer game was not initialized".to_owned(),
                ));
            };
            if options.pause {
                initial_frame.clone()
            } else {
                let manual = keyboard_mask();
                if model.is_some() && !planner_observed_current {
                    dodge_danger::observe::feed(game);
                    dodge_danger::hnnplan::set_history(rect_memory.clone());
                }
                let input = if options.auto_dodge {
                    let Some(model) = model.as_ref() else {
                        return Err(ViewerError::InvalidTrace(
                            "auto-dodge model was not loaded".to_owned(),
                        ));
                    };
                    merge_auto_dodge_input(
                        dodge_danger::hnnplan::choose(model, game, 36).0.mask(),
                        manual,
                    )
                } else {
                    manual
                };
                if input & BUTTON_X_MASK != 0 && game_dead && dodge_danger::observe::enabled() {
                    dodge_danger::observe::reset();
                    rect_memory = dodge_danger::hnnplan::RectSnapshot::new();
                }
                selected_action = dodge_core::Action::ALL
                    .into_iter()
                    .find(|action| action.mask() == input & 0x0f)
                    .unwrap_or(dodge_core::Action::Neutral);
                if model.is_some() {
                    rect_memory = dodge_danger::hnnplan::rect_snapshot(game);
                }
                let result = game
                    .advance_frame(input)
                    .map_err(|error| ViewerError::InvalidTrace(error.to_string()))?;
                game_dead = result.dead;
                planner_observed_current = false;
                PresentedFrame::from_snapshot(result.snapshot)?
            }
        };
        let rgba_len = frame.rgba().len();
        let texture = Texture2D::from_rgba8(
            dodge_core::FRAMEBUFFER_WIDTH as u16,
            dodge_core::FRAMEBUFFER_HEIGHT as u16,
            frame.rgba(),
        );
        texture.set_filter(FilterMode::Nearest);
        clear_background(BLACK);
        if let Some(viewport) = integer_viewport(screen_width(), screen_height()) {
            draw_texture_ex(
                &texture,
                viewport.x,
                viewport.y,
                WHITE,
                DrawTextureParams {
                    dest_size: Some(vec2(viewport.size, viewport.size)),
                    ..Default::default()
                },
            );
            if show_overlay {
                if let Some(game) = live_game.as_ref() {
                    let display_action = if let Some(model) = model.as_ref() {
                        dodge_danger::observe::feed(game);
                        dodge_danger::hnnplan::set_history(rect_memory.clone());
                        let action = dodge_danger::hnnplan::choose(model, game, 36).0;
                        rect_memory = dodge_danger::hnnplan::rect_snapshot(game);
                        planner_observed_current = true;
                        action
                    } else {
                        selected_action
                    };
                    draw_danger_overlay(
                        game,
                        model.as_ref(),
                        display_action,
                        viewport.x,
                        viewport.y,
                        viewport.size,
                    );
                }
            }
        }
        if options.debug {
            let text = format!(
                "frame={} seed={} state={:016x} pixels={:016x} rgba={}",
                frame.frame(),
                trace.as_ref().map_or(options.seed, |value| value.seed),
                frame.state_hash(),
                frame.pixel_hash(),
                rgba_len
            );
            draw_text(&text, 8.0, 20.0, 18.0, WHITE);
        }
        if is_key_pressed(KeyCode::Escape) {
            break;
        }
        if overlay_toggle_requested(trace.is_some(), is_key_pressed(KeyCode::O)) {
            show_overlay = !show_overlay;
            if show_overlay && model.is_none() {
                if live_game.is_some() {
                    dodge_danger::observe::reset();
                    rect_memory = dodge_danger::hnnplan::RectSnapshot::new();
                    planner_observed_current = false;
                }
                model = load_optional_danger_model(&options.danger_model);
            }
        }
        if let Some(trace) = trace.as_ref()
            && !options.pause
        {
            elapsed += get_frame_time();
            while elapsed >= FRAME_CADENCE_SECONDS {
                elapsed -= FRAME_CADENCE_SECONDS;
                if frame_index + 1 < trace.frames.len() {
                    frame_index += 1;
                }
            }
        }
        next_frame().await;
    }
    Ok(())
}

fn load_danger_model(
    path: &std::path::Path,
) -> Result<dodge_danger::hnnplan::PhysicsModel, ViewerError> {
    let text = std::fs::read_to_string(path)?;
    dodge_danger::hnnplan::PhysicsModel::from_json(&text).map_err(ViewerError::InvalidTrace)
}

fn load_optional_danger_model(
    path: &std::path::Path,
) -> Option<dodge_danger::hnnplan::PhysicsModel> {
    match load_danger_model(path) {
        Ok(model) => Some(model),
        Err(error) => {
            eprintln!("could not load danger model: {error}");
            None
        }
    }
}

const fn overlay_toggle_requested(is_trace: bool, key_pressed: bool) -> bool {
    !is_trace && key_pressed
}

fn keyboard_mask() -> u8 {
    let mut mask = 0_u8;
    if is_key_down(KeyCode::Left) {
        mask |= Button::Left.mask();
    }
    if is_key_down(KeyCode::Right) {
        mask |= Button::Right.mask();
    }
    if is_key_down(KeyCode::Up) {
        mask |= Button::Up.mask();
    }
    if is_key_down(KeyCode::Down) {
        mask |= Button::Down.mask();
    }
    if retry_button_down(
        is_key_down(KeyCode::R),
        is_key_down(KeyCode::X),
        is_key_down(KeyCode::Space),
    ) {
        mask |= Button::X.mask();
    }
    if is_key_down(KeyCode::Z) {
        mask |= Button::O.mask();
    }
    mask
}

fn merge_auto_dodge_input(action: u8, manual: u8) -> u8 {
    action | (manual & BUTTON_X_MASK)
}

fn draw_danger_overlay(
    game: &NativeGame,
    model: Option<&dodge_danger::hnnplan::PhysicsModel>,
    action: dodge_core::Action,
    left: f32,
    top: f32,
    size: f32,
) {
    let point = |x: f32, y: f32| (left + x * size / 128.0, top + y * size / 128.0);
    if let Some(model) = model {
        let grid = 20;
        for (index, arrival) in dodge_danger::hnnplan::arrival_field(model, game, grid, 36)
            .into_iter()
            .enumerate()
        {
            let danger = (1.0 - arrival / 36.0).clamp(0.0, 1.0);
            let x = index % grid;
            let y = index / grid;
            draw_rectangle(
                left + x as f32 * size / grid as f32,
                top + y as f32 * size / grid as f32,
                size / grid as f32 + 1.0,
                size / grid as f32 + 1.0,
                Color::new(1.0, 0.12, 0.2, danger * 0.42),
            );
        }
    }
    let view = game.privileged_view();
    let rate = (view.speed.to_double() * view.freeze_rate.to_double()) as f32;
    for enemy in view.enemies {
        let enemy_rate = rate * enemy.speed.to_f32();
        let (x, y) = point(
            enemy.x.to_f32() + enemy.size.to_f32() * 0.5,
            enemy.y.to_f32() + enemy.size.to_f32() * 0.5,
        );
        let (end_x, end_y) = point(
            enemy.x.to_f32() + enemy.size.to_f32() * 0.5 + enemy.vx.to_f32() * enemy_rate * 36.0,
            enemy.y.to_f32() + enemy.size.to_f32() * 0.5 + enemy.vy.to_f32() * enemy_rate * 36.0,
        );
        draw_line(x, y, end_x, end_y, 2.0, Color::new(1.0, 0.75, 0.15, 0.85));
    }
    let mut rollout = game.clone();
    let mut previous = (
        view.player.x.to_f32() + view.player.size.to_f32() * 0.5,
        view.player.y.to_f32() + view.player.size.to_f32() * 0.5,
    );
    for _ in 0..36 {
        if rollout.advance_frame_headless(action.mask()).is_err() {
            break;
        }
        let player = rollout.privileged_view().player;
        let current = (
            player.x.to_f32() + player.size.to_f32() * 0.5,
            player.y.to_f32() + player.size.to_f32() * 0.5,
        );
        let (x1, y1) = point(previous.0, previous.1);
        let (x2, y2) = point(current.0, current.1);
        draw_line(x1, y1, x2, y2, 2.0, Color::new(0.15, 0.9, 1.0, 0.78));
        previous = current;
    }
}

const fn retry_button_down(r: bool, x: bool, space: bool) -> bool {
    r || x || space
}

fn parse_options<I>(arguments: I) -> Result<Options, ViewerError>
where
    I: IntoIterator<Item = String>,
{
    let mut values = arguments.into_iter();
    let mut trace = None;
    let mut frame = 0_usize;
    let mut capture = None;
    let mut debug = false;
    let mut pause = false;
    let mut seed = 42_u32;
    let mut auto_dodge = false;
    let mut danger_model = env::var_os("DODGE_DANGER_MODEL").map_or_else(
        || PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../models/physics.json"),
        PathBuf::from,
    );
    while let Some(argument) = values.next() {
        match argument.as_str() {
            "--trace" => trace = Some(PathBuf::from(next_value(&mut values, "--trace")?)),
            "--frame" => {
                frame = next_value(&mut values, "--frame")?
                    .parse::<usize>()
                    .map_err(|error| {
                        ViewerError::InvalidTrace(format!("invalid frame: {error}"))
                    })?;
            }
            "--capture" => capture = Some(PathBuf::from(next_value(&mut values, "--capture")?)),
            "--debug" => debug = true,
            "--pause" => pause = true,
            "--seed" => {
                seed = next_value(&mut values, "--seed")?
                    .parse::<u32>()
                    .map_err(|error| ViewerError::InvalidTrace(format!("invalid seed: {error}")))?;
            }
            "--auto-dodge" => auto_dodge = true,
            "--danger-model" => {
                danger_model = PathBuf::from(next_value(&mut values, "--danger-model")?)
            }
            "--help" | "-h" => return Err(ViewerError::InvalidTrace(usage().to_owned())),
            value => {
                return Err(ViewerError::InvalidTrace(format!(
                    "unknown argument {value}\n{}",
                    usage()
                )));
            }
        }
    }
    if trace.is_some() && auto_dodge {
        return Err(ViewerError::InvalidTrace(
            "--auto-dodge cannot be used with --trace".to_owned(),
        ));
    }
    Ok(Options {
        trace,
        frame,
        capture,
        debug,
        pause,
        seed,
        auto_dodge,
        danger_model,
    })
}

fn next_value<I>(values: &mut I, option: &str) -> Result<String, ViewerError>
where
    I: Iterator<Item = String>,
{
    values
        .next()
        .ok_or_else(|| ViewerError::InvalidTrace(format!("{option} requires a value\n{}", usage())))
}

const fn usage() -> &'static str {
    "usage: dodge-viewer [--trace PATH] [--frame N] [--capture PATH] [--debug] [--pause] [--seed N] [--auto-dodge] [--danger-model PATH]"
}

#[cfg(test)]
mod tests {
    use super::{
        load_optional_danger_model, merge_auto_dodge_input, overlay_toggle_requested,
        parse_options, retry_button_down,
    };
    use dodge_core::Button;

    #[test]
    fn v162_r_key_aliases_retry_button() {
        assert!(retry_button_down(true, false, false));
        assert!(retry_button_down(false, true, false));
        assert!(retry_button_down(false, false, true));
        assert!(!retry_button_down(false, false, false));
    }

    #[test]
    fn auto_dodge_preserves_retry_x_input() {
        assert_eq!(dodge_core::BUTTON_X_MASK, Button::X.mask());
        let action = dodge_core::Action::Left.mask();
        assert_eq!(
            merge_auto_dodge_input(action, Button::X.mask()),
            action | Button::X.mask()
        );
        assert_eq!(merge_auto_dodge_input(action, Button::Right.mask()), action);
    }

    #[test]
    fn incompatible_trace_options_are_rejected() {
        assert!(
            parse_options(["--trace".into(), "trace.json".into(), "--auto-dodge".into()]).is_err()
        );
        assert!(parse_options(["--pause".into()]).is_ok());
    }

    #[test]
    fn trace_mode_ignores_overlay_toggle() {
        assert!(!overlay_toggle_requested(true, true));
        assert!(overlay_toggle_requested(false, true));
        assert!(!overlay_toggle_requested(false, false));
    }

    #[test]
    fn missing_optional_model_does_not_exit_overlay_flow() {
        let missing =
            std::env::temp_dir().join(format!("dodge-viewer-missing-model-{}", std::process::id()));
        assert!(load_optional_danger_model(&missing).is_none());
    }
}
