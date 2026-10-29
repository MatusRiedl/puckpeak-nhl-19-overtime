"""Draw overtime_roster/assets/app.ico (standard library only): an orange clock face, the "O" of Overtime, on the
app's near-black, in 16/24/32/48/64/256 px PNG frames.

    python packaging/make_icon.py
"""
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'overtime_roster', 'assets', 'app.ico')
SIZES = (16, 24, 32, 48, 64, 256)
BG, ORANGE, WHITE = (0x11, 0x11, 0x16), (0xf2, 0x6b, 0x1d), (0xf3, 0xf1, 0xee)
SS = 4      # samples per pixel along each axis


def _segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def colour_at(x, y):
    """(r, g, b, a) of the point (x, y) in a 0..1 square."""
    # the rounded square
    r = 0.2
    qx, qy = max(abs(x - 0.5) - (0.5 - r), 0), max(abs(y - 0.5) - (0.5 - r), 0)
    if math.hypot(qx, qy) > r:
        return (0, 0, 0, 0)
    d = math.hypot(x - 0.5, y - 0.5)
    if 0.27 <= d <= 0.39:                                       # the ring
        return ORANGE + (255,)
    if d < 0.27:
        if _segment(x, y, 0.5, 0.5, 0.5, 0.29) < 0.042 or _segment(x, y, 0.5, 0.5, 0.66, 0.5) < 0.042:
            return WHITE + (255,)                               # the hands at a quarter past twelve
        if d < 0.05:
            return WHITE + (255,)
    return BG + (255,)


def render(size):
    rows = []
    for j in range(size):
        row = bytearray([0])        # PNG filter: none
        for i in range(size):
            acc = [0, 0, 0, 0]
            for sj in range(SS):
                for si in range(SS):
                    c = colour_at((i + (si + 0.5) / SS) / size, (j + (sj + 0.5) / SS) / size)
                    a = c[3]
                    acc[0] += c[0] * a
                    acc[1] += c[1] * a
                    acc[2] += c[2] * a
                    acc[3] += a
            alpha = acc[3] / (SS * SS)
            if acc[3]:
                row += bytes((round(acc[0] / acc[3]), round(acc[1] / acc[3]), round(acc[2] / acc[3]), round(alpha)))
            else:
                row += b'\0\0\0\0'
        rows.append(bytes(row))
    return png(size, b''.join(rows))


def png(size, raw):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def ico(frames):
    head = struct.pack('<HHH', 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries, blobs = b'', b''
    for size, data in frames:
        entries += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return head + entries + blobs


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'wb') as f:
        f.write(ico([(s, render(s)) for s in SIZES]))
    print(OUT)


if __name__ == '__main__':
    main()
