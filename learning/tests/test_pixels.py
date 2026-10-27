import re
import unittest
from pathlib import Path

from dodge_learning.pixels import (
    FRAME_SIZE,
    PICO8_PALETTE,
    PixelHistory,
    indexed_to_rgb,
    validate_frame,
)


class PixelTests(unittest.TestCase):
    def test_palette_matches_native_viewer_and_uses_rgb_not_indices(self):
        viewer = Path(__file__).resolve().parents[2] / "crates/dodge-viewer/src/lib.rs"
        source = viewer.read_text().split("pub const PICO8_PALETTE", 1)[1].split("= [", 1)[1].split("\n];", 1)[0]
        palette = tuple(tuple(map(int, color)) for color in re.findall(
            r"\[(\d+),\s*(\d+),\s*(\d+)\]", source
        ))
        self.assertEqual(PICO8_PALETTE, palette)
        frame = bytes(range(16)) * (FRAME_SIZE // 16)
        rgb = indexed_to_rgb(frame)
        self.assertEqual(len(rgb), FRAME_SIZE * 3)
        self.assertEqual(rgb[:48], bytes(value for color in palette for value in color))
        self.assertEqual(rgb[36:39], bytes((41, 173, 255)))

    def test_rejects_invalid_size_and_palette_values(self):
        for invalid in (b"", bytes(FRAME_SIZE - 1), bytes(FRAME_SIZE + 1),
                        bytes([16]) + bytes(FRAME_SIZE - 1)):
            with self.assertRaises(ValueError):
                indexed_to_rgb(invalid)
        with self.assertRaises(TypeError):
            validate_frame([0] * FRAME_SIZE)

    def test_mutable_input_is_copied_and_failed_append_does_not_mutate_history(self):
        frame = bytearray(FRAME_SIZE)
        history = PixelHistory()
        history.reset(frame, frame_id=13)
        frame[0] = 8
        self.assertEqual(history.frames[0][0], 0)
        before = history.frames
        with self.assertRaises(ValueError):
            history.append(frame, frame_id=15)
        with self.assertRaises(ValueError):
            history.append(bytes([255]) * FRAME_SIZE, frame_id=14)
        self.assertEqual(history.frames, before)

    def test_history_channel_order_and_reset_isolates_episodes(self):
        history = PixelHistory(2)
        first = bytes([8]) * FRAME_SIZE
        second = bytes([12]) * FRAME_SIZE
        history.reset(first, frame_id=13)
        self.assertEqual(history.frames, (first, first))
        history.append(second, frame_id=14)
        values = history.rgb_chw()
        self.assertEqual(values.typecode, "f")
        self.assertEqual(len(values), 6 * FRAME_SIZE)
        for channel, expected in enumerate((255, 0, 77, 41, 173, 255)):
            self.assertAlmostEqual(values[channel * FRAME_SIZE], expected / 255, places=6)
        history.reset(bytes(FRAME_SIZE), frame_id=13)
        self.assertEqual(set(history.rgb_chw()), {0.0})

    def test_requires_reset_and_valid_frame_tracking(self):
        frame = bytes(FRAME_SIZE)
        history = PixelHistory()
        with self.assertRaises(RuntimeError):
            history.append(frame)
        with self.assertRaises(RuntimeError):
            _ = history.frames
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                PixelHistory(invalid)
        history.reset(frame)
        with self.assertRaises(ValueError):
            history.append(frame, frame_id=1)
        history.reset(frame, frame_id=13)
        with self.assertRaises(ValueError):
            history.append(frame)


if __name__ == "__main__":
    unittest.main()
