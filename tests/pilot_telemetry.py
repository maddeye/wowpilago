"""Decode visible RGB only. No capture, client input, or actions."""
import argparse
import json
import math
from pathlib import Path
import struct
import sys
import time

SCHEMA = struct.Struct('<2sBHBBHHHHIIIBH')


def checksum(data):
    a = b = 0
    for value in data:
        a = (a + value) % 255
        b = (b + a) % 255
    return bytes((a, b))


def decode(rgb, width=64, height=64, x=0, y=0):
    if len(rgb) != width*height*3 or min(x, y) < 0 or x+64 > width or y+64 > height:
        raise ValueError('RGB size/ROI')
    bits = []
    for i in range(256):
        offset = ((y + (i//16)*4 + 2)*width + x + (i%16)*4 + 2)*3
        pixel = rgb[offset:offset+3]
        if max(pixel) <= 80:
            bits.append(0)
        elif min(pixel) >= 175:
            bits.append(1)
        else:
            raise ValueError('ambiguous pixel')
    data = bytes(sum(bits[i+j] << j for j in range(8)) for i in range(0, 256, 8))
    if data[-2:] != checksum(data[:-2]):
        raise ValueError('checksum/torn frame')
    magic, version, seq, flags, valid, area, mx, my, facing, hp, thp, money, quest, tail = SCHEMA.unpack(data[:-2])
    if magic != b'WP' or version != 1 or tail != seq or (flags | valid) & 128:
        raise ValueError('schema')
    if (valid & 1 and (not area or (mx == my == 0))) or (valid & 32 and quest > 8):
        raise ValueError('map/quest range')
    if valid & 64 and not flags & 1 and (flags & 22 or valid & 8):
        raise ValueError('target contradiction')
    result = dict(sequence=seq, map_area=area if valid & 1 else None,
                  map_x=mx/65535 if valid & 1 else None, map_y=my/65535 if valid & 1 else None,
                  facing=facing*math.tau/65536 if valid & 2 else None,
                  player_health=hp if valid & 4 else None, target_health=thp if valid & 8 else None,
                  money=money if valid & 16 else None, quest7_count=quest if valid & 32 else None)
    for i, name in enumerate(('target_exists', 'target_dead', 'target_can_attack', 'player_combat', 'target_combat', 'loot_open', 'player_dead')):
        result[name] = bool(flags & (1 << i)) if valid & 64 else None
    return result


class Freshness:
    def __init__(self):
        self.previous = None

    def observe(self, rgb, now=None, **roi):
        now = time.monotonic() if now is None else now
        try:
            result = decode(rgb, **roi)
        except ValueError:
            self.previous = None
            raise
        seq = result['sequence']
        previous = self.previous
        if previous is None or not 0 <= now-previous[1] <= .5:
            self.previous = (seq, now)
            raise ValueError('unprimed/stale: need another advancing live frame')
        if not 0 < (seq-previous[0]) % 65536 < 32768:
            raise ValueError('repeated/reversed sequence')
        self.previous = (seq, now)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', nargs='?', help='concatenated raw RGB frames; default stdin')
    parser.add_argument('--size', nargs=2, type=int, default=(64, 64), metavar=('W', 'H'))
    parser.add_argument('--origin', nargs=2, type=int, default=(0, 0), metavar=('X', 'Y'))
    args = parser.parse_args()
    w, h = args.size
    if w < 64 or h < 64:
        parser.error('size must contain a 64x64 ROI')
    source = Path(args.file).open('rb') if args.file else sys.stdin.buffer
    gate = Freshness()
    while True:
        raw = source.read(w*h*3)
        if not raw:
            break
        try:
            roi = dict(width=w, height=h, x=args.origin[0], y=args.origin[1])
            result = decode(raw, **roi) if args.file else gate.observe(raw, **roi)
            print(json.dumps(dict(result, fresh=not bool(args.file))), flush=True)
        except ValueError as error:
            print(str(error), file=sys.stderr)
