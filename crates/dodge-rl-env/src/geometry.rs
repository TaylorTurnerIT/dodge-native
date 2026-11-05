//! Literal native collision geometry and conservative renderer admission.
//!
//! Inputs are native signed Q16.16 `i32` bit patterns. Endpoint arithmetic
//! explicitly wraps at that native boundary, then widens to `i64` for math.
//! Collision intervals are never reordered, clamped, or made absolute.
//! Admission is a current observation-boundary policy, not a pixel oracle or
//! persistent visibility tracker. Callers own eligibility, identity and history.

/// One pixel in native Q16.16 raw units.
pub const ONE_RAW: i32 = 1 << 16;
/// Constant-velocity prediction horizon, in raw gameplay frames.
pub const SLAB_HORIZON_FRAMES: f64 = 120.0;

/// Literal signed interval. Private endpoints keep arithmetic within the native
/// `i32` input domain; accessors expose widened Q16.16 values without clipping.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RawInterval {
    min: i64,
    max: i64,
}

impl RawInterval {
    pub const fn from_raw_q16(min: i32, max: i32) -> Self {
        Self {
            min: min as i64,
            max: max as i64,
        }
    }

    pub const fn min_raw(self) -> i64 {
        self.min
    }

    pub const fn max_raw(self) -> i64 {
        self.max
    }

    pub const fn is_inverted(self) -> bool {
        self.min > self.max
    }

    /// Twice the center, retaining a half of one raw unit exactly.
    pub const fn center_twice_raw(self) -> i64 {
        self.min + self.max
    }

    /// Twice the signed half-extent. Negative extents remain negative.
    pub const fn half_extent_twice_raw(self) -> i64 {
        self.max - self.min
    }

    /// Native strict inequalities, including literal point/inverted intervals.
    pub const fn strictly_overlaps(self, other: Self) -> bool {
        self.max > other.min && self.min < other.max
    }

    /// Signed Minkowski gap; unlike overlap length, preserves interior points.
    pub fn signed_gap(self, player: Self) -> i64 {
        (self.min - player.max).max(player.min - self.max)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RawAabb {
    pub x: RawInterval,
    pub y: RawInterval,
}

impl RawAabb {
    pub const fn from_raw_q16(min_x: i32, min_y: i32, max_x: i32, max_y: i32) -> Self {
        Self {
            x: RawInterval::from_raw_q16(min_x, max_x),
            y: RawInterval::from_raw_q16(min_y, max_y),
        }
    }

    pub const fn strictly_overlaps(self, other: Self) -> bool {
        self.x.strictly_overlaps(other.x) && self.y.strictly_overlaps(other.y)
    }

    pub fn signed_gaps(self, player: Self) -> (i64, i64) {
        (self.x.signed_gap(player.x), self.y.signed_gap(player.y))
    }

    pub const fn measures(self) -> RawBoxMeasures {
        RawBoxMeasures {
            center_x_twice_raw: self.x.center_twice_raw(),
            center_y_twice_raw: self.y.center_twice_raw(),
            half_x_twice_raw: self.x.half_extent_twice_raw(),
            half_y_twice_raw: self.y.half_extent_twice_raw(),
        }
    }
}

/// All fields are in half-raw units: divide by `2 * 65536` for pixels.
/// Difference these integers before conversion when measuring frame history.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RawBoxMeasures {
    pub center_x_twice_raw: i64,
    pub center_y_twice_raw: i64,
    pub half_x_twice_raw: i64,
    pub half_y_twice_raw: i64,
}

pub fn raw_to_pixels(raw: i64) -> f64 {
    raw as f64 / f64::from(ONE_RAW)
}

pub fn half_raw_to_pixels(twice_raw: i64) -> f64 {
    twice_raw as f64 / (2.0 * f64::from(ONE_RAW))
}

/// Enemy, kamikaze and explosion box `[x,x+s] × [y,y+s]`.
pub const fn enemy_box(x: i32, y: i32, size: i32) -> RawAabb {
    RawAabb::from_raw_q16(x, y, x.wrapping_add(size), y.wrapping_add(size))
}

/// Powerup box uses its fixed radius, never the enemy record's size.
pub const fn powerup_box(x: i32, y: i32) -> RawAabb {
    let radius = 4 * ONE_RAW;
    RawAabb::from_raw_q16(
        x.wrapping_sub(radius),
        y.wrapping_sub(radius),
        x.wrapping_add(radius),
        y.wrapping_add(radius),
    )
}

/// Pattern collision endpoint is `x + width - 1`, including width zero.
pub const fn rectangle_box(x: i32, y: i32, width: i32, height: i32) -> RawAabb {
    RawAabb::from_raw_q16(
        x,
        y,
        x.wrapping_add(width).wrapping_sub(ONE_RAW),
        y.wrapping_add(height).wrapping_sub(ONE_RAW),
    )
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PlayerBoxKind {
    EnemyFamily,
    Powerup,
    Rectangle,
}

/// Native operation order is retained, including wrapping and point players.
/// `Powerup` is also the widest player box used by the player raster channel.
pub const fn player_box(x: i32, y: i32, size: i32, kind: PlayerBoxKind) -> RawAabb {
    let (min_x, min_y, max_x, max_y) = match kind {
        PlayerBoxKind::EnemyFamily => (
            x.wrapping_sub(size).wrapping_add(ONE_RAW),
            y.wrapping_sub(size).wrapping_add(ONE_RAW),
            x.wrapping_add(size).wrapping_sub(ONE_RAW),
            y.wrapping_add(size).wrapping_sub(ONE_RAW),
        ),
        PlayerBoxKind::Powerup => (
            x.wrapping_sub(size),
            y.wrapping_sub(size),
            x.wrapping_add(size),
            y.wrapping_add(size),
        ),
        PlayerBoxKind::Rectangle => (
            x.wrapping_add(2 * ONE_RAW).wrapping_sub(size),
            y.wrapping_add(2 * ONE_RAW).wrapping_sub(size),
            x.wrapping_sub(2 * ONE_RAW).wrapping_add(size),
            y.wrapping_sub(2 * ONE_RAW).wrapping_add(size),
        ),
    };
    RawAabb::from_raw_q16(min_x, min_y, max_x, max_y)
}

/// Measured entity center delta minus player velocity, in Q16.16 raw units per
/// raw frame. `f64` retains half-raw deltas from odd endpoint sums.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct RelativeVelocityRaw {
    pub x: f64,
    pub y: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SlabContact {
    /// Contact estimate clipped to `[0,120]`; misses use 120.
    pub frames: f64,
    /// Distinguishes a contact at frame 120 from the miss sentinel.
    pub contact_within_horizon: bool,
    /// Current native strict collision, independent of predicted contact.
    pub strict_overlap_now: bool,
}

/// Closed-contact slab estimate for literal native inequalities, with fixed
/// current extents and constant relative center velocity. Stationary axes must
/// already contain zero in their translation interval. Growing/shrinking
/// extents, future acceleration and collision/list order are not modeled.
/// Inverted intervals remain literal: a sufficiently wide player can satisfy
/// native inequalities even for an inverted rectangle. Nonfinite velocity is a
/// prediction miss; current strict overlap is still reported independently.
pub fn slab_contact(
    entity: RawAabb,
    player: RawAabb,
    velocity: RelativeVelocityRaw,
) -> SlabContact {
    let strict_overlap_now = entity.strictly_overlaps(player);
    let miss = SlabContact {
        frames: SLAB_HORIZON_FRAMES,
        contact_within_horizon: false,
        strict_overlap_now,
    };
    let Some((x_enter, x_exit)) = axis_contact(entity.x, player.x, velocity.x) else {
        return miss;
    };
    let Some((y_enter, y_exit)) = axis_contact(entity.y, player.y, velocity.y) else {
        return miss;
    };
    let enter = 0.0_f64.max(x_enter).max(y_enter);
    let exit = SLAB_HORIZON_FRAMES.min(x_exit).min(y_exit);
    if enter > exit {
        return miss;
    }
    SlabContact {
        frames: enter,
        contact_within_horizon: true,
        strict_overlap_now,
    }
}

fn axis_contact(entity: RawInterval, player: RawInterval, velocity: f64) -> Option<(f64, f64)> {
    if !velocity.is_finite() {
        return None;
    }
    let low = player.min - entity.max;
    let high = player.max - entity.min;
    if low > high {
        return None;
    }
    if velocity == 0.0 {
        return (low <= 0 && high >= 0).then_some((f64::NEG_INFINITY, f64::INFINITY));
    }
    let first = low as f64 / velocity;
    let second = high as f64 / velocity;
    Some((first.min(second), first.max(second)))
}

/// Floor, not truncation toward zero.
pub const fn floor_raw_q16(raw: i32) -> i64 {
    (raw >> 16) as i64
}

/// Native `PicoFixed::round`: negative half ties go toward positive infinity.
/// Wrapping the half-pixel addition also retains the native top-edge wrap.
pub const fn round_raw_q16(raw: i32) -> i64 {
    (raw.wrapping_add(ONE_RAW / 2) >> 16) as i64
}

/// Inclusive integer visual envelope, distinct from collision geometry.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PixelFootprint {
    pub min_x: i64,
    pub min_y: i64,
    pub max_x: i64,
    pub max_y: i64,
}

impl PixelFootprint {
    pub const fn intersects_world(self) -> bool {
        self.min_x <= self.max_x
            && self.min_y <= self.max_y
            && self.max_x >= 0
            && self.max_y >= 0
            && self.min_x <= 127
            && self.min_y <= 127
    }
}

pub fn enemy_footprint(x: i32, y: i32, size: i32) -> PixelFootprint {
    let x = floor_raw_q16(x);
    let y = floor_raw_q16(y);
    let size = floor_raw_q16(size).max(0);
    PixelFootprint {
        min_x: x,
        min_y: y,
        max_x: x + size,
        max_y: y + size + 1,
    }
}

pub const fn powerup_footprint(x: i32, y: i32) -> PixelFootprint {
    let x = floor_raw_q16(x);
    let y = floor_raw_q16(y);
    PixelFootprint {
        min_x: x - 4,
        min_y: y - 4,
        max_x: x + 4,
        max_y: y + 5,
    }
}

/// Conservative charging/fill/outline envelope; not a per-pixel charge oracle.
/// Only visual endpoints are normalized. No state, timer or pattern ID enters.
pub fn rectangle_footprint(x: i32, y: i32, width: i32, height: i32) -> PixelFootprint {
    let x = round_raw_q16(x);
    let y = round_raw_q16(y);
    let end_x = x + round_raw_q16(width);
    let end_y = y + round_raw_q16(height);
    PixelFootprint {
        min_x: x.min(end_x),
        min_y: y.min(end_y),
        max_x: x.max(end_x),
        max_y: y.max(end_y) + 1,
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SegmentError {
    NonAxisAligned,
}

/// A rounded inclusive horizontal/vertical warning segment. Eligibility must
/// come from the core's current drawn-warning helper; this stores no hidden box.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct WarningSegment {
    x0: i64,
    y0: i64,
    x1: i64,
    y1: i64,
}

impl WarningSegment {
    pub fn from_raw_q16(x0: i32, y0: i32, x1: i32, y1: i32) -> Result<Self, SegmentError> {
        let segment = Self {
            x0: round_raw_q16(x0),
            y0: round_raw_q16(y0),
            x1: round_raw_q16(x1),
            y1: round_raw_q16(y1),
        };
        if segment.x0 != segment.x1 && segment.y0 != segment.y1 {
            return Err(SegmentError::NonAxisAligned);
        }
        Ok(segment)
    }

    pub fn main_footprint(self) -> PixelFootprint {
        PixelFootprint {
            min_x: self.x0.min(self.x1),
            min_y: self.y0.min(self.y1),
            max_x: self.x0.max(self.x1),
            max_y: self.y0.max(self.y1),
        }
    }

    pub fn shadow_footprint(self) -> PixelFootprint {
        let main = self.main_footprint();
        PixelFootprint {
            min_y: main.min_y + 1,
            max_y: main.max_y + 1,
            ..main
        }
    }

    pub fn intersects_world(self) -> bool {
        self.main_footprint().intersects_world() || self.shadow_footprint().intersects_world()
    }
}
