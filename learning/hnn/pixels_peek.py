#!/usr/bin/env python3
"""Convert the first three indexed frames of a pixel shard to PNG."""
import pathlib
import struct
import sys
import zlib

PALETTE = bytes(sum(([r, g, b] for r, g, b in [
    (0, 0, 0), (29, 43, 83), (126, 37, 83), (0, 135, 81),
    (171, 82, 54), (95, 87, 79), (194, 195, 199), (255, 241, 232),
    (255, 0, 77), (255, 163, 0), (255, 236, 39), (0, 228, 54),
    (41, 173, 255), (131, 118, 156), (255, 119, 168), (255, 204, 170),
]), []))

def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

def main():
    source, destination = map(pathlib.Path, sys.argv[1:3])
    destination.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as pixels:
        for index in range(3):
            frame = pixels.read(128 * 128)
            if len(frame) != 128 * 128 or max(frame) > 15:
                raise ValueError('missing frame or invalid palette index')
            rows = b''.join(b'\0' + frame[y * 128:(y + 1) * 128] for y in range(128))
            png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 128, 128, 8, 3, 0, 0, 0))
                   + chunk(b'PLTE', PALETTE) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))
            (destination / f'frame-{index}.png').write_bytes(png)

if __name__ == '__main__':
    main()
