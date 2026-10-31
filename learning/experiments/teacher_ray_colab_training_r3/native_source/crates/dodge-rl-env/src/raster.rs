//! Independent binary semantic targets on canonical world-coordinate patches.
//!
//! Collision boxes use half-open positive intervals and explicit point rules.
//! Warnings instead use inclusive rounded pixels and their `y+1` shadow. There
//! is no camera transform, history, phase inference, or player-overlap labeling.

use crate::geometry::{PixelFootprint, RawAabb, RawInterval, WarningSegment};

pub const PATCH_SIDE: usize = 16;
pub const CHANNEL_COUNT: usize = 5;
pub const CELL_RAW: i64 = 1 << 19;

pub type RasterChannel = [[f32; PATCH_SIDE]; PATCH_SIDE];
pub type RasterChannels = [RasterChannel; CHANNEL_COUNT];

/// Stable channel order `[lethal_now, lethal_soon, enemy, powerup, player]`.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(usize)]
pub enum Channel {
    LethalNow = 0,
    LethalSoon = 1,
    Enemy = 2,
    Powerup = 3,
    Player = 4,
}

/// Independent caller-supplied labels. Hazardous phase is not player overlap.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct RasterFlags {
    pub lethal_now: bool,
    pub lethal_soon: bool,
    pub enemy: bool,
    pub powerup: bool,
    pub player: bool,
}

impl RasterFlags {
    pub const fn as_array(self) -> [bool; CHANNEL_COUNT] {
        [
            self.lethal_now,
            self.lethal_soon,
            self.enemy,
            self.powerup,
            self.player,
        ]
    }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct RasterDiagnostics {
    /// One increment per box with at least one inverted axis.
    pub inverted_boxes: u64,
    /// One increment per inverted axis (zero, one or two per submitted box).
    pub inverted_axes: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PatchSpan {
    pub first: usize,
    pub last: usize,
}

/// Arithmetic right shift implements floor for negative raw coordinates.
pub const fn floor_cell(raw: i64) -> i64 {
    raw >> 19
}

/// Equivalent to `-((-raw) >> 19)` without overflowing at `i64::MIN`.
pub const fn ceil_cell(raw: i64) -> i64 {
    floor_cell(raw) + if raw & (CELL_RAW - 1) == 0 { 0 } else { 1 }
}

/// Select patches without changing geometry. Positive `[min,max)` intervals
/// use `floor(min)..=ceil(max)-1`; points use only `floor(point)`. Inverted
/// intervals cover nothing. `AuxRaster::paint_box` additionally counts them.
pub fn interval_patches(interval: RawInterval) -> Option<PatchSpan> {
    if interval.is_inverted() {
        return None;
    }
    let first = floor_cell(interval.min_raw());
    let last = if interval.min_raw() == interval.max_raw() {
        first
    } else {
        ceil_cell(interval.max_raw()) - 1
    };
    clipped_span(first, last)
}

fn clipped_span(first: i64, last: i64) -> Option<PatchSpan> {
    let first = first.max(0);
    let last = last.min(15);
    if first > last {
        return None;
    }
    Some(PatchSpan {
        first: first as usize,
        last: last as usize,
    })
}

#[derive(Clone, Debug, PartialEq)]
pub struct AuxRaster {
    channels: RasterChannels,
    diagnostics: RasterDiagnostics,
}

impl Default for AuxRaster {
    fn default() -> Self {
        Self {
            channels: [[[0.0; PATCH_SIDE]; PATCH_SIDE]; CHANNEL_COUNT],
            diagnostics: RasterDiagnostics::default(),
        }
    }
}

impl AuxRaster {
    pub fn channels(&self) -> &RasterChannels {
        &self.channels
    }

    pub fn channel(&self, channel: Channel) -> &RasterChannel {
        // Exhaustive matching avoids unchecked indexing in production code.
        let [lethal_now, lethal_soon, enemy, powerup, player] = &self.channels;
        match channel {
            Channel::LethalNow => lethal_now,
            Channel::LethalSoon => lethal_soon,
            Channel::Enemy => enemy,
            Channel::Powerup => powerup,
            Channel::Player => player,
        }
    }

    pub const fn diagnostics(&self) -> RasterDiagnostics {
        self.diagnostics
    }

    pub fn into_channels(self) -> RasterChannels {
        self.channels
    }

    /// Union literal collision coverage into every enabled channel. Use
    /// `player_box(..., PlayerBoxKind::Powerup)` for the player channel.
    pub fn paint_box(&mut self, bounds: RawAabb, flags: RasterFlags) {
        let inverted_axes = u64::from(bounds.x.is_inverted()) + u64::from(bounds.y.is_inverted());
        if inverted_axes != 0 {
            self.diagnostics.inverted_boxes = self.diagnostics.inverted_boxes.saturating_add(1);
            self.diagnostics.inverted_axes =
                self.diagnostics.inverted_axes.saturating_add(inverted_axes);
            return;
        }
        if let (Some(x), Some(y)) = (interval_patches(bounds.x), interval_patches(bounds.y)) {
            self.paint_spans(x, y, flags);
        }
    }

    /// Paint only the actual main and shadow segments, never a hidden box or a
    /// diagonal segment's bounding rectangle. Callers supply current labels;
    /// drawn warnings normally enable only `lethal_soon`.
    pub fn paint_warning(&mut self, segment: WarningSegment, flags: RasterFlags) {
        self.paint_pixel_segment(segment.main_footprint(), flags);
        self.paint_pixel_segment(segment.shadow_footprint(), flags);
    }

    fn paint_pixel_segment(&mut self, segment: PixelFootprint, flags: RasterFlags) {
        // WarningSegment guarantees one axis is a point. Inclusive pixel ends
        // map by floor on both sides, unlike half-open collision intervals.
        let x = clipped_span(segment.min_x >> 3, segment.max_x >> 3);
        let y = clipped_span(segment.min_y >> 3, segment.max_y >> 3);
        if let (Some(x), Some(y)) = (x, y) {
            self.paint_spans(x, y, flags);
        }
    }

    fn paint_spans(&mut self, x: PatchSpan, y: PatchSpan, flags: RasterFlags) {
        for (channel, enabled) in self.channels.iter_mut().zip(flags.as_array()) {
            if enabled {
                for row in channel.iter_mut().take(y.last + 1).skip(y.first) {
                    for cell in row.iter_mut().take(x.last + 1).skip(x.first) {
                        *cell = 1.0;
                    }
                }
            }
        }
    }
}
