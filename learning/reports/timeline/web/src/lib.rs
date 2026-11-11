//! Dodge and its bots, for the browser.
//!
//! One `Sim` is one game plus the policy playing it. The page drives it one
//! frame at a time through the `extern "C"` functions at the bottom, and reads
//! the screen, the stats and the policy's internals straight out of linear
//! memory. No JS glue, no allocator calls from the page beyond `buf_alloc`.

pub mod cnn;
pub mod space;

use std::cell::RefCell;

use dodge_core::m0_policy::{Policy, PolicyKind as M0Kind};
use dodge_core::{
    Action, BUTTON_X_MASK, FRAMEBUFFER_SIZE, FutureMode, Mode, NativeConfig, NativeGame,
    plan_action_values_m0,
};
use dodge_danger::{DangerConfig, Driver, PolicyKind as DangerKind};
use dodge_rl_env::{SlotState, VELOCITY_FLOW_SIZE, encode_velocity_flow};

pub const BOT_HUMAN: u32 = 0;
pub const BOT_M0: u32 = 1;
pub const BOT_SPACE: u32 = 2;
pub const BOT_CNN: u32 = 3;
pub const BOT_BELIEF: u32 = 4;
pub const BOT_LOOKAHEAD: u32 = 5;
pub const BOT_LANDSCAPE: u32 = 6;
pub const BOT_RANDOM: u32 = 7;

/// Belief planner settings used here: a 4-frame root hold, then up to 48
/// frames of M0 in each of 4 resampled futures; re-plan every 4 frames.
pub const BELIEF_ROOT: u32 = 4;
pub const BELIEF_ROLLOUT: u32 = 48;

pub const INFO_LEN: usize = 16;

pub enum Bot {
    Human,
    M0(Box<Policy>),
    Random(Box<Policy>),
    Space(Box<space::SpaceBot>),
    Cnn { obs: Vec<f32>, last: Option<cnn::Output> },
    Belief { m0: Box<Policy>, rng: u64, hold: u32, action: Action, values: [f64; 9] },
    Danger(Box<Driver>),
}

pub struct Sim {
    pub game: NativeGame,
    pub bot: Bot,
    pub dead: bool,
    pub last_action: usize,
    pub frames: u32,
    screen: Vec<u8>,
    info: Vec<f64>,
    overlay: Vec<f32>,
    overlay_dims: [u32; 2],
    scores: Vec<f32>,
    path: Vec<f32>,
}

thread_local! {
    static CNN: cnn::Cnn = cnn::Cnn::load();
    static SIMS: RefCell<Vec<Option<Box<Sim>>>> = const { RefCell::new(Vec::new()) };
}

fn start(game: &mut NativeGame) {
    for frame in 0..120 {
        let r = game
            .advance_frame_headless(if frame == 0 { BUTTON_X_MASK } else { 0 })
            .expect("startup frame");
        if r.mode == Mode::Game && !r.dead {
            return;
        }
    }
    panic!("startup did not reach Game");
}

fn xorshift(state: &mut u64) -> u64 {
    let mut x = *state;
    x ^= x << 13;
    x ^= x >> 7;
    x ^= x << 17;
    *state = x;
    x
}

impl Sim {
    pub fn new(bot: u32, seed: u32, difficulty: u8, patterns: bool, powerups: bool) -> Self {
        let config = NativeConfig {
            seed,
            difficulty,
            patterns_enabled: patterns,
            powerups_enabled: powerups,
            ..NativeConfig::new(seed)
        };
        let mut game = NativeGame::new(config);
        start(&mut game);
        let danger = |kind| {
            let config = DangerConfig { seed, difficulty, patterns, powerups, ..DangerConfig::default() };
            Bot::Danger(Box::new(Driver::new(config, kind)))
        };
        let bot = match bot {
            BOT_M0 => Bot::M0(Box::new(Policy::new(M0Kind::AabbDodger, seed))),
            BOT_RANDOM => Bot::Random(Box::new(Policy::new(M0Kind::Random, seed))),
            BOT_SPACE => Bot::Space(Box::new(space::SpaceBot::new())),
            BOT_CNN => Bot::Cnn { obs: vec![0.0; VELOCITY_FLOW_SIZE], last: None },
            BOT_BELIEF => Bot::Belief {
                m0: Box::new(Policy::new(M0Kind::AabbDodger, seed)),
                rng: 0x9E37_79B9_7F4A_7C15 ^ u64::from(seed),
                hold: 0,
                action: Action::Neutral,
                values: [0.0; 9],
            },
            BOT_LOOKAHEAD => danger(DangerKind::Lookahead),
            BOT_LANDSCAPE => danger(DangerKind::Landscape),
            _ => Bot::Human,
        };
        let mut sim = Self {
            game,
            bot,
            dead: false,
            last_action: 0,
            frames: 0,
            screen: vec![0; FRAMEBUFFER_SIZE],
            info: vec![0.0; INFO_LEN],
            overlay: vec![0.0; 48 * 48],
            overlay_dims: [0, 0],
            scores: vec![0.0; 9],
            path: Vec::with_capacity(256),
        };
        sim.refresh_info();
        sim
    }

    /// Choose this frame's action and advance one frame. Returns true once dead.
    pub fn step(&mut self, human_mask: u8) -> bool {
        if self.dead {
            return true;
        }
        let action = self.decide(human_mask);
        self.last_action = Action::ALL.iter().position(|a| *a == action).unwrap_or(0);
        let r = self.game.advance_frame_headless(action.mask()).expect("frame");
        self.frames += 1;
        self.dead = r.dead;
        self.refresh_info();
        self.dead
    }

    fn decide(&mut self, human_mask: u8) -> Action {
        match &mut self.bot {
            Bot::Human => Action::ALL
                .into_iter()
                .find(|a| a.mask() == human_mask)
                .unwrap_or(Action::Neutral),
            Bot::M0(p) | Bot::Random(p) => {
                let snap = self.game.snapshot();
                let state = snap.logical_state();
                p.observe(state);
                p.action(state)
            }
            Bot::Space(bot) => {
                let s = SlotState::read(&self.game);
                bot.observe(&s);
                let a = bot.act(&s);
                Action::ALL[a]
            }
            Bot::Cnn { obs, last } => {
                encode_velocity_flow(&self.game, obs);
                let out = CNN.with(|c| c.forward(obs));
                let a = out.action;
                *last = Some(out);
                Action::ALL[a]
            }
            Bot::Belief { m0, rng, hold, action, values } => {
                let snap = self.game.snapshot();
                let state = snap.logical_state();
                m0.observe(state);
                if *hold == 0 {
                    let seeds: Vec<u32> = (0..4).map(|_| xorshift(rng) as u32).collect();
                    let planned = plan_action_values_m0(
                        &self.game,
                        BELIEF_ROOT,
                        BELIEF_ROLLOUT,
                        &FutureMode::FairResampled(seeds),
                        m0,
                    );
                    let m0_choice = m0.clone().action(state);
                    *action = match planned {
                        Ok(v) => {
                            *values = v.values;
                            v.best_action(m0_choice)
                        }
                        Err(_) => m0_choice,
                    };
                    *hold = BELIEF_ROOT;
                }
                *hold -= 1;
                *action
            }
            Bot::Danger(driver) => driver.act(&self.game).unwrap_or(Action::Neutral),
        }
    }

    fn refresh_info(&mut self) {
        let cause = self
            .game
            .death_diagnostic()
            .cause()
            .map_or(-1.0, |c| c.index() as f64);
        let i = &mut self.info;
        i[0] = f64::from(self.game.survival_frames());
        i[1] = f64::from(self.game.score().to_f32());
        i[2] = if self.dead { 1.0 } else { 0.0 };
        i[3] = if self.dead { cause } else { -1.0 };
        i[4] = self.last_action as f64;
        i[5] = match &self.bot {
            Bot::Cnn { last: Some(o), .. } => f64::from(o.value),
            _ => f64::NAN,
        };
        i[6] = f64::from(self.frames);
        let p = self.game.player();
        i[7] = p.x.to_double();
        i[8] = p.y.to_double();
        i[9] = p.size.to_double();
    }

    pub fn render(&mut self) -> &[u8] {
        let frame: &mut [u8; FRAMEBUFFER_SIZE] = (&mut self.screen[..]).try_into().expect("size");
        self.game.render_into(frame);
        &self.screen
    }

    /// Fill the overlay, the nine action scores and the planned path for the
    /// current decision. `slice` picks the CNN's danger slice (0..6).
    pub fn inspect(&mut self, slice: usize) {
        self.path.clear();
        self.overlay_dims = [0, 0];
        self.scores.iter_mut().for_each(|s| *s = f32::NAN);
        match &self.bot {
            Bot::Cnn { last: Some(o), .. } => {
                let k = slice.min(cnn::SLICES - 1);
                self.overlay.resize(cnn::CELLS, 0.0);
                self.overlay.copy_from_slice(&o.field[k * cnn::CELLS..(k + 1) * cnn::CELLS]);
                self.overlay_dims = [32, 32];
                for a in 0..9 {
                    self.scores[a] = o.log_pmf[a].exp();
                }
            }
            Bot::Space(bot) => {
                // Python SpaceBot.overlay(): the room map itself, in frames, on
                // cfg["overlay_grid"] = 48 cells, cfg["overlay_tmax"] = 120 ahead.
                let g = 48;
                self.overlay = bot.room_view(g, 120.0);
                self.overlay_dims = [g as u32, g as u32];
                for (x, y) in &bot.last.path {
                    self.path.push(*x as f32);
                    self.path.push(*y as f32);
                }
                for a in 0..9 {
                    self.scores[a] = bot.last.score[a] as f32 - if bot.last.hit[a] <= 24.0 { 10.0 } else { 0.0 };
                }
            }
            Bot::Danger(driver) => {
                if let Some(f) = driver.field() {
                    // dodge-danger's own convention (see landscape_heat): its page
                    // draws 1 - arrival / horizon as danger.
                    let h = driver.config.horizon as f32;
                    self.overlay.resize(f.width * f.height, 0.0);
                    for (o, a) in self.overlay.iter_mut().zip(&f.arrival) {
                        *o = (1.0 - a / h).clamp(0.0, 1.0);
                    }
                    self.overlay_dims = [f.width as u32, f.height as u32];
                    self.info[10] = f.goal.0;
                    self.info[11] = f.goal.1;
                }
                for (x, y) in &driver.last_path {
                    self.path.push(*x as f32);
                    self.path.push(*y as f32);
                }
                if let Some(c) = driver.last_costs {
                    for a in 0..9 {
                        self.scores[a] = -c[a] as f32;
                    }
                }
            }
            Bot::Belief { values, .. } => {
                for a in 0..9 {
                    self.scores[a] = values[a] as f32;
                }
            }
            _ => {}
        }
    }
}

// ---------------------------------------------------------------------------
// The page's interface. Handles are indices into SIMS.

fn with_sim<R>(id: u32, f: impl FnOnce(&mut Sim) -> R) -> Option<R> {
    SIMS.with(|s| s.borrow_mut().get_mut(id as usize).and_then(|o| o.as_mut()).map(|sim| f(sim)))
}

#[unsafe(no_mangle)]
pub extern "C" fn sim_create(bot: u32, seed: u32, difficulty: u32, patterns: u32, powerups: u32) -> u32 {
    let sim = Box::new(Sim::new(bot, seed, difficulty as u8, patterns != 0, powerups != 0));
    SIMS.with(|s| {
        let mut sims = s.borrow_mut();
        if let Some(i) = sims.iter().position(|o| o.is_none()) {
            sims[i] = Some(sim);
            i as u32
        } else {
            sims.push(Some(sim));
            (sims.len() - 1) as u32
        }
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn sim_destroy(id: u32) {
    SIMS.with(|s| {
        if let Some(slot) = s.borrow_mut().get_mut(id as usize) {
            *slot = None;
        }
    });
}

/// Advance up to `frames` frames; stops early on death. Returns 1 when dead.
#[unsafe(no_mangle)]
pub extern "C" fn sim_step(id: u32, human_mask: u32, frames: u32) -> u32 {
    with_sim(id, |sim| {
        for _ in 0..frames {
            if sim.step(human_mask as u8) {
                return 1;
            }
        }
        0
    })
    .unwrap_or(1)
}

#[unsafe(no_mangle)]
pub extern "C" fn sim_render(id: u32) -> *const u8 {
    with_sim(id, |sim| sim.render().as_ptr()).unwrap_or(std::ptr::null())
}

#[unsafe(no_mangle)]
pub extern "C" fn sim_info(id: u32) -> *const f64 {
    with_sim(id, |sim| sim.info.as_ptr()).unwrap_or(std::ptr::null())
}

/// Fill the inspection buffers; returns overlay width * 65536 + height.
#[unsafe(no_mangle)]
pub extern "C" fn sim_inspect(id: u32, slice: u32) -> u32 {
    with_sim(id, |sim| {
        sim.inspect(slice as usize);
        sim.overlay_dims[0] * 65536 + sim.overlay_dims[1]
    })
    .unwrap_or(0)
}

#[unsafe(no_mangle)]
pub extern "C" fn sim_overlay(id: u32) -> *const f32 {
    with_sim(id, |sim| sim.overlay.as_ptr()).unwrap_or(std::ptr::null())
}

#[unsafe(no_mangle)]
pub extern "C" fn sim_scores(id: u32) -> *const f32 {
    with_sim(id, |sim| sim.scores.as_ptr()).unwrap_or(std::ptr::null())
}

/// Planned path as (x, y) pairs; returns the number of points.
#[unsafe(no_mangle)]
pub extern "C" fn sim_path(id: u32) -> *const f32 {
    with_sim(id, |sim| sim.path.as_ptr()).unwrap_or(std::ptr::null())
}

#[unsafe(no_mangle)]
pub extern "C" fn sim_path_len(id: u32) -> u32 {
    with_sim(id, |sim| (sim.path.len() / 2) as u32).unwrap_or(0)
}
