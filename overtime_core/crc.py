"""CRC-32/MPEG-2 (poly 04C11DB7, init FFFFFFFF, not reflected, xorout 0), as used by EA's t3db databases.

Computed through zlib for speed: CRC-32/MPEG-2 of `data` equals the bit-reversed zlib CRC-32 of the
bit-reversed bytes, inverted.
"""
import zlib

_REV8 = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))


def _rev32(x):
    return int(f"{x:032b}"[::-1], 2)


def crc32_mpeg2(data, crc=0xFFFFFFFF):
    """CRC of `data`; pass a previous result as `crc` to continue a running CRC."""
    return _rev32(zlib.crc32(bytes(data).translate(_REV8), _rev32(crc) ^ 0xFFFFFFFF)) ^ 0xFFFFFFFF


def crc32_mpeg2_slow(data, crc=0xFFFFFFFF):
    """Bitwise reference implementation (tests only)."""
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc
