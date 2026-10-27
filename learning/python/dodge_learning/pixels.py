"""Palette conversion and episode-local image history, without ML dependencies."""

from __future__ import annotations

from array import array
from collections import deque

FRAME_WIDTH = 128
FRAME_HEIGHT = 128
FRAME_SIZE = FRAME_WIDTH * FRAME_HEIGHT

# Keep this versioned copy equal to dodge-viewer's PICO8_PALETTE.
PICO8_PALETTE = (
    (0, 0, 0),
    (29, 43, 83),
    (126, 37, 83),
    (0, 135, 81),
    (171, 82, 54),
    (95, 87, 79),
    (194, 195, 199),
    (255, 241, 232),
    (255, 0, 77),
    (255, 163, 0),
    (255, 236, 39),
    (0, 228, 54),
    (41, 173, 255),
    (131, 118, 156),
    (255, 119, 168),
    (255, 204, 170),
)

_CHANNEL_TABLES = tuple(
    bytes(color[channel] for color in PICO8_PALETTE) + bytes(240)
    for channel in range(3)
)
_NORMALIZED_CHANNELS = tuple(
    tuple(color[channel] / 255.0 for color in PICO8_PALETTE)
    for channel in range(3)
)
_NORMALIZED_LUMINANCE = tuple(
    (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0
    for red, green, blue in PICO8_PALETTE
)


def validate_frame(frame: bytes | bytearray | memoryview) -> bytes:
    """Copy an indexed frame, rejecting wrong shapes and unknown colors."""
    if not isinstance(frame, (bytes, bytearray, memoryview)):
        raise TypeError("indexed frame must be bytes, bytearray, or memoryview")
    pixels = bytes(frame)
    if len(pixels) != FRAME_SIZE:
        raise ValueError(f"indexed frame must contain {FRAME_SIZE} pixels")
    if max(pixels) >= len(PICO8_PALETTE):
        raise ValueError("indexed frame contains a palette index outside 0..15")
    return pixels


def indexed_to_rgb(frame: bytes | bytearray | memoryview) -> bytes:
    """Return interleaved RGB bytes using the game's exact palette."""
    pixels = validate_frame(frame)
    rgb = bytearray(FRAME_SIZE * 3)
    for channel, table in enumerate(_CHANNEL_TABLES):
        rgb[channel::3] = pixels.translate(table)
    return bytes(rgb)


class PixelHistory:
    """Store oldest-to-newest indexed frames without crossing episode boundaries.

    ``reset`` duplicates the first image. When frame IDs are supplied, every
    subsequent image must come from the next native frame. Callers that omit
    IDs are responsible for supplying consecutive frames.
    """

    def __init__(self, length: int = 4):
        if isinstance(length, bool) or not isinstance(length, int) or length < 1:
            raise ValueError("history length must be a positive integer")
        self.length = length
        self._frames: deque[bytes] = deque(maxlen=length)
        self._last_frame_id: int | None = None

    @staticmethod
    def _validate_frame_id(frame_id: int | None) -> None:
        if frame_id is not None and (
            isinstance(frame_id, bool) or not isinstance(frame_id, int) or frame_id < 0
        ):
            raise ValueError("frame ID must be a nonnegative integer")

    def reset(
        self, frame: bytes | bytearray | memoryview, frame_id: int | None = None
    ) -> None:
        self._validate_frame_id(frame_id)
        pixels = validate_frame(frame)
        self._frames.clear()
        self._frames.extend([pixels] * self.length)
        self._last_frame_id = frame_id

    def append(
        self, frame: bytes | bytearray | memoryview, frame_id: int | None = None
    ) -> None:
        if not self._frames:
            raise RuntimeError("reset image history before appending frames")
        self._validate_frame_id(frame_id)
        if self._last_frame_id is not None:
            if frame_id != self._last_frame_id + 1:
                raise ValueError("image history requires consecutive native frame IDs")
        elif frame_id is not None:
            raise ValueError("reset history with frame IDs before appending tracked frames")
        pixels = validate_frame(frame)
        self._frames.append(pixels)
        self._last_frame_id = frame_id

    @property
    def frames(self) -> tuple[bytes, ...]:
        if not self._frames:
            raise RuntimeError("reset image history before reading frames")
        return tuple(self._frames)

    def rgb_bytes(self) -> tuple[bytes, ...]:
        """Return one interleaved RGB byte string per image, oldest first."""
        return tuple(indexed_to_rgb(frame) for frame in self.frames)

    def rgb_chw(self) -> array:
        """Return float32 CHW values in [0, 1], shape (3 * length, 128, 128).

        Channels are frame 0 red, green, blue, then frame 1 red, green, blue,
        and so on. No rewards, privileged state, or metadata enter this array.
        """
        result = array("f")
        for frame in self.frames:
            for values in _NORMALIZED_CHANNELS:
                result.extend(map(values.__getitem__, frame))
        return result

    def gray_chw(self) -> array:
        """Return float32 luminance, shape (length, 128, 128), oldest first.

        Each indexed pixel is converted through the exact RGB palette, then
        weighted by 0.2126 red + 0.7152 green + 0.0722 blue and divided by 255.
        This four-channel input matches the visual student's frame-stack
        contract. The legacy RGB baseline keeps using ``rgb_chw``.
        """
        result = array("f")
        for frame in self.frames:
            result.extend(map(_NORMALIZED_LUMINANCE.__getitem__, frame))
        return result
