use dodge_core::{Action, FullState, PicoFixed, PlayerState};

const HORIZON: u32 = 12;
const SAFE_CLEARANCE: f64 = 4.0;

#[derive(Clone, Copy, Debug)]
pub enum PolicyKind {
    Random,
    Neutral,
    AabbDodger,
}

impl PolicyKind {
    pub const ALL: [Self; 3] = [Self::Random, Self::Neutral, Self::AabbDodger];

    pub const fn name(self) -> &'static str {
        match self {
            Self::Random => "random",
            Self::Neutral => "neutral",
            Self::AabbDodger => "nearest_lethal_aabb_safe_powerup",
        }
    }
}

/// Independent of the game's PicoRng. Never advances or inspects native RNG.
pub struct PrivateRng(u64);

impl PrivateRng {
    pub const fn initial_state(seed: u32) -> u64 {
        (seed as u64) ^ 0xD1B5_4A32_D192_ED03
    }

    pub const fn new(seed: u32) -> Self {
        Self(Self::initial_state(seed))
    }

    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    pub fn action(&mut self) -> Action {
        // Rejection removes modulo bias: the accepted range is divisible by nine.
        let limit = u64::MAX - u64::MAX % 9;
        loop {
            let value = self.next();
            if value < limit {
                return Action::ALL
                    .get((value % 9) as usize)
                    .copied()
                    .unwrap_or(Action::Neutral);
            }
        }
    }
}

#[derive(Clone, Copy, Default, Debug)]
struct Box2 {
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
}

impl Box2 {
    fn centered(x: f64, y: f64, half: f64) -> Self {
        Self {
            x0: x - half,
            y0: y - half,
            x1: x + half,
            y1: y + half,
        }
    }

    fn overlaps(self, other: Self) -> bool {
        self.x1 > other.x0 && self.y1 > other.y0 && self.x0 < other.x1 && self.y0 < other.y1
    }

    fn clearance(self, other: Self) -> f64 {
        let x = (other.x0 - self.x1).max(self.x0 - other.x1);
        let y = (other.y0 - self.y1).max(self.y0 - other.y1);
        if x <= 0.0 && y <= 0.0 {
            x.max(y)
        } else {
            x.max(0.0).hypot(y.max(0.0))
        }
    }

    fn extrapolate(self, change: Self, frames: f64) -> Self {
        Self {
            x0: self.x0 + frames * change.x0,
            y0: self.y0 + frames * change.y0,
            x1: self.x1 + frames * change.x1,
            y1: self.y1 + frames * change.y1,
        }
    }

    fn difference(self, previous: Self) -> Self {
        Self {
            x0: self.x0 - previous.x0,
            y0: self.y0 - previous.y0,
            x1: self.x1 - previous.x1,
            y1: self.y1 - previous.y1,
        }
    }
}

fn rect_box(rect: &dodge_core::PatternRect) -> Box2 {
    Box2 {
        x0: rect.x.to_double(),
        y0: rect.y.to_double(),
        x1: rect.x.add(rect.width).sub(PicoFixed::ONE).to_double(),
        y1: rect.y.add(rect.height).sub(PicoFixed::ONE).to_double(),
    }
}

#[derive(Clone, Copy)]
struct Entity {
    bounds: Box2,
    change: Box2,
    player_half: f64,
    lethal_after: f64,
    beneficial: bool,
}

fn active_rect_boxes(state: &FullState) -> Vec<Box2> {
    state
        .active_pattern
        .and_then(|i| state.patterns.get(i))
        .map_or_else(Vec::new, |p| p.rects.iter().map(rect_box).collect())
}

pub struct Policy {
    kind: PolicyKind,
    rng: PrivateRng,
    previous_pattern: Option<usize>,
    previous_rects: Vec<Box2>,
    rect_changes: Vec<Box2>,
}

impl Policy {
    pub fn new(kind: PolicyKind, seed: u32) -> Self {
        Self {
            kind,
            rng: PrivateRng::new(seed),
            previous_pattern: None,
            previous_rects: Vec::new(),
            rect_changes: Vec::new(),
        }
    }

    /// Observe every raw frame. Rect indices remain stable within an active pattern.
    pub fn observe(&mut self, state: &FullState) {
        if !matches!(self.kind, PolicyKind::AabbDodger) {
            return;
        }
        let current = active_rect_boxes(state);
        self.rect_changes = current
            .iter()
            .enumerate()
            .map(|(i, &bounds)| {
                if self.previous_pattern == state.active_pattern {
                    self.previous_rects
                        .get(i)
                        .map_or_else(Box2::default, |&old| bounds.difference(old))
                } else {
                    Box2::default()
                }
            })
            .collect();
        self.previous_rects = current;
        self.previous_pattern = state.active_pattern;
    }

    fn entities(&self, state: &FullState) -> Vec<Entity> {
        let player_size = state.player.size.to_double();
        let mut entities = Vec::new();
        for enemy in &state.enemies {
            let beneficial = enemy.personality >= 2;
            let bounds = if beneficial {
                Box2::centered(enemy.x.to_double(), enemy.y.to_double(), 4.0)
            } else {
                Box2 {
                    x0: enemy.x.to_double(),
                    y0: enemy.y.to_double(),
                    x1: enemy.x.add(enemy.size).to_double(),
                    y1: enemy.y.add(enemy.size).to_double(),
                }
            };
            // Hold explosion extents fixed during prediction. Their current native
            // x/y/size still define the exact current collision box. Other entries
            // use analytic displacement; Vec removals make index differencing unsafe.
            let scale =
                state.speed.to_double() * state.freeze_rate.to_double() * enemy.speed.to_double();
            let dx = if enemy.personality == -1 {
                0.0
            } else {
                enemy.vx.to_double() * scale
            };
            let dy = if enemy.personality == -1 {
                0.0
            } else {
                enemy.vy.to_double() * scale
            };
            entities.push(Entity {
                bounds,
                change: Box2 {
                    x0: dx,
                    x1: dx,
                    y0: dy,
                    y1: dy,
                },
                player_half: if beneficial {
                    player_size
                } else {
                    player_size - 1.0
                },
                lethal_after: 0.0,
                beneficial,
            });
        }
        if let Some(pattern) = state.active_pattern.and_then(|i| state.patterns.get(i)) {
            for (i, rect) in pattern.rects.iter().enumerate() {
                let lethal_after = if pattern.pattern_type == 1 || rect.sh == PicoFixed::from_int(2)
                {
                    0.0
                } else if rect.sh > PicoFixed::ZERO && rect.sh < PicoFixed::from_int(2) {
                    (2.0 - rect.sh.to_double()) / (0.02 * state.freeze_rate.to_double())
                } else {
                    continue;
                };
                entities.push(Entity {
                    bounds: rect_box(rect),
                    change: self.rect_changes.get(i).copied().unwrap_or_default(),
                    player_half: player_size - 2.0,
                    lethal_after,
                    beneficial: false,
                });
            }
        }
        entities
    }

    pub fn action(&mut self, state: &FullState) -> Action {
        match self.kind {
            PolicyKind::Random => self.rng.action(),
            PolicyKind::Neutral => Action::Neutral,
            PolicyKind::AabbDodger => choose_action(state.player, &self.entities(state)),
        }
    }
}

fn advance_player(mut player: PlayerState, action: Action) -> PlayerState {
    // Mirror momentum and position clamps in fixed point; do not normalize diagonals.
    player.vx = player.vx.mul_fixed(PicoFixed::from_f32(0.8));
    player.vy = player.vy.mul_fixed(PicoFixed::from_f32(0.8));
    let mask = action.mask();
    if mask & 1 != 0 {
        player.vx = player.vx.sub(PicoFixed::from_f32(0.5));
    }
    if mask & 2 != 0 {
        player.vx = player.vx.add(PicoFixed::from_f32(0.5));
    }
    if mask & 4 != 0 {
        player.vy = player.vy.sub(PicoFixed::from_f32(0.5));
    }
    if mask & 8 != 0 {
        player.vy = player.vy.add(PicoFixed::from_f32(0.5));
    }
    player.x = player
        .x
        .add(player.vx)
        .clamp(PicoFixed::from_int(2), PicoFixed::from_int(125));
    player.y = player
        .y
        .add(player.vy)
        .clamp(PicoFixed::from_int(2), PicoFixed::from_int(125));
    player
}

#[derive(Clone, Copy)]
struct Candidate {
    action: Action,
    collision_free_frames: u32,
    nearest_clearance: f64,
    all_clearance: f64,
    powerup_distance: f64,
}

fn choose_action(player: PlayerState, entities: &[Entity]) -> Action {
    let distance = |e: &Entity| {
        e.bounds.clearance(Box2::centered(
            player.x.to_double(),
            player.y.to_double(),
            e.player_half,
        ))
    };
    let nearest = entities
        .iter()
        .enumerate()
        .filter(|(_, e)| !e.beneficial && e.lethal_after == 0.0)
        .min_by(|(_, a), (_, b)| distance(a).total_cmp(&distance(b)))
        .or_else(|| {
            entities
                .iter()
                .enumerate()
                .filter(|(_, e)| !e.beneficial && e.lethal_after <= f64::from(HORIZON))
                .min_by(|(_, a), (_, b)| distance(a).total_cmp(&distance(b)))
        })
        .map(|(i, _)| i);
    let has_powerup = entities.iter().any(|e| e.beneficial);
    let mut candidates = Vec::new();
    for action in Action::ALL {
        let mut predicted = player;
        let mut candidate = Candidate {
            action,
            collision_free_frames: HORIZON + 1,
            nearest_clearance: 1e9,
            all_clearance: 1e9,
            powerup_distance: 1e9,
        };
        for t in 0..=HORIZON {
            // The engine checks collisions before updating player motion.
            for (i, entity) in entities.iter().enumerate() {
                let bounds = entity.bounds.extrapolate(entity.change, f64::from(t));
                let body = Box2::centered(
                    predicted.x.to_double(),
                    predicted.y.to_double(),
                    entity.player_half,
                );
                let clearance = body.clearance(bounds);
                if entity.beneficial {
                    if t == HORIZON {
                        candidate.powerup_distance = candidate.powerup_distance.min(clearance);
                    }
                } else if f64::from(t) >= entity.lethal_after {
                    candidate.all_clearance = candidate.all_clearance.min(clearance);
                    if Some(i) == nearest && t == HORIZON {
                        candidate.nearest_clearance = clearance;
                    }
                    if body.overlaps(bounds) {
                        candidate.collision_free_frames = candidate.collision_free_frames.min(t);
                    }
                }
            }
            predicted = advance_player(predicted, action);
        }
        candidates.push(candidate);
    }
    let safe =
        |c: &&Candidate| c.collision_free_frames > HORIZON && c.all_clearance >= SAFE_CLEARANCE;
    if has_powerup
        && let Some(best) = candidates
            .iter()
            .filter(safe)
            .min_by(|a, b| a.powerup_distance.total_cmp(&b.powerup_distance))
    {
        return best.action;
    }
    // Stable first maximum keeps Neutral on exact ties, without jitter/center/wall terms.
    let mut best = None::<Candidate>;
    for candidate in candidates {
        let improves = best.is_none_or(|old| {
            candidate
                .collision_free_frames
                .cmp(&old.collision_free_frames)
                .then(
                    candidate
                        .nearest_clearance
                        .total_cmp(&old.nearest_clearance),
                )
                .then(candidate.all_clearance.total_cmp(&old.all_clearance))
                .is_gt()
        });
        if improves {
            best = Some(candidate);
        }
    }
    best.map_or(Action::Neutral, |c| c.action)
}

#[cfg(test)]
mod tests {
    use super::*;
    use dodge_core::{EnemyState, NativeConfig, NativeGame};

    #[test]
    fn private_seed_reproducibility_and_nine_action_masks() {
        let mut a = PrivateRng::new(0xB000_0000);
        let mut b = PrivateRng::new(0xB000_0000);
        let mut c = PrivateRng::new(0xB000_0001);
        let aa: Vec<_> = (0..1024).map(|_| a.action().mask()).collect();
        let bb: Vec<_> = (0..1024).map(|_| b.action().mask()).collect();
        let cc: Vec<_> = (0..1024).map(|_| c.action().mask()).collect();
        assert_eq!(aa, bb);
        assert_ne!(aa, cc);
        let masks: std::collections::BTreeSet<_> = aa.into_iter().collect();
        assert_eq!(
            masks.into_iter().collect::<Vec<_>>(),
            vec![0, 1, 2, 4, 5, 6, 8, 9, 10]
        );
    }

    #[test]
    fn strict_type_specific_boxes_include_zero_half_extent_player() {
        let game = NativeGame::new(NativeConfig::new(1));
        let mut state = game.snapshot().logical_state().clone();
        let policy = Policy::new(PolicyKind::AabbDodger, 1);
        for personality in [-1, 0, 1, 2, 3, 4] {
            let mut enemy = EnemyState::normal(
                PicoFixed::from_int(10),
                PicoFixed::from_int(20),
                PicoFixed::from_int(4),
            );
            enemy.personality = personality;
            state.enemies = vec![enemy];
            let entities = policy.entities(&state);
            assert_eq!(entities.len(), 1);
            if let Some(entity) = entities.first() {
                assert_eq!(entity.player_half, if personality >= 2 { 4.0 } else { 3.0 });
                assert_eq!(entity.bounds.x0, if personality >= 2 { 6.0 } else { 10.0 });
            }
        }
        let bounds = Box2 {
            x0: 10.0,
            y0: 10.0,
            x1: 20.0,
            y1: 20.0,
        };
        assert!(!bounds.overlaps(Box2::centered(7.0, 15.0, 3.0)));
        assert!(bounds.overlaps(Box2::centered(7.001, 15.0, 3.0)));
        assert!(bounds.overlaps(Box2::centered(15.0, 15.0, 0.0)));
    }

    #[test]
    fn active_rects_use_w_minus_one_charge_and_current_displacement() {
        let game = NativeGame::new(NativeConfig::new(1));
        let mut state = game.snapshot().logical_state().clone();
        state.active_pattern = Some(0);
        let mut policy = Policy::new(PolicyKind::AabbDodger, 1);
        if let Some(pattern) = state.patterns.first_mut() {
            pattern.pattern_type = 0;
            for rect in &mut pattern.rects {
                rect.sh = PicoFixed::ONE;
            }
        }
        policy.observe(&state);
        let charging = policy.entities(&state);
        assert!(charging.iter().all(|e| e.lethal_after > 0.0));
        if let Some(pattern) = state.patterns.first_mut() {
            pattern.pattern_type = 1;
            for rect in &mut pattern.rects {
                rect.x = rect.x.add(PicoFixed::ONE);
            }
        }
        policy.observe(&state);
        for entity in policy.entities(&state) {
            assert_eq!(entity.lethal_after, 0.0);
            assert_eq!(entity.change.x0, 1.0);
            assert_eq!(entity.player_half, 2.0);
        }
        if let Some(rect) = state.patterns.first().and_then(|p| p.rects.first()) {
            assert_eq!(
                rect_box(rect).x1,
                rect.x.add(rect.width).sub(PicoFixed::ONE).to_double()
            );
        }
        state.active_pattern = None;
        assert!(policy.entities(&state).is_empty());
    }

    #[test]
    fn seeks_powerups_only_with_safe_candidates_and_respects_momentum_clamp() {
        let player = PlayerState::new();
        let powerup = Entity {
            bounds: Box2::centered(100.0, 64.0, 4.0),
            change: Box2::default(),
            player_half: 4.0,
            lethal_after: 0.0,
            beneficial: true,
        };
        assert_eq!(choose_action(player, &[powerup]), Action::Right);
        assert_eq!(choose_action(player, &[]), Action::Neutral);
        let stationary_lethal = Entity {
            bounds: Box2::centered(80.0, 64.0, 4.0),
            beneficial: false,
            player_half: 3.0,
            ..powerup
        };
        assert_ne!(choose_action(player, &[stationary_lethal]).mask() & 1, 0);
        let wall = Entity {
            bounds: Box2 {
                x0: 75.0,
                y0: -50.0,
                x1: 100.0,
                y1: 144.0,
            },
            beneficial: false,
            player_half: 2.0,
            ..powerup
        };
        let action = choose_action(player, &[powerup, wall]);
        assert_eq!(action.mask() & 2, 0);
        let mut moving = player;
        moving.x = PicoFixed::from_int(125);
        moving.vx = PicoFixed::from_int(2);
        let next = advance_player(moving, Action::Right);
        assert_eq!(next.x, PicoFixed::from_int(125));
        assert!(next.vx > PicoFixed::from_int(2));
    }
}
