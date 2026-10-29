import os
import struct

import pytest

from overtime_core import lz4f
from overtime_core.crc import crc32_mpeg2, crc32_mpeg2_slow


def test_crc_check_value():
    assert crc32_mpeg2(b'123456789') == 0x0376E6E7


@pytest.mark.parametrize('n', [0, 1, 3, 64, 1000])
def test_crc_matches_bitwise(n):
    data = os.urandom(n)
    assert crc32_mpeg2(data) == crc32_mpeg2_slow(data)


def test_xxh32_known_values():
    assert lz4f._xxh32(b'') == 0x02CC5D05
    assert lz4f._xxh32(b'a') == 0x550D7456
    assert lz4f._xxh32(b'abc') == 0x32D153FF


@pytest.mark.parametrize('n', [0, 5, 70000])
def test_frame_roundtrip(n):
    data = os.urandom(n)
    frame = lz4f.encode(data, block_max=64 << 10)
    out, used = lz4f.decode(frame + b'trailing')
    assert out == data and used == len(frame)


def test_decode_compressed_block_with_overlapping_match():
    # literals "ab", then a match of length 6 at offset 2 -> "abababab", then final literals "!"
    block = bytes([0x22]) + b'ab' + struct.pack('<H', 2) + bytes([0x10]) + b'!'
    desc = bytes([0x60, 0x40])
    frame = struct.pack('<I', lz4f.MAGIC) + desc + bytes([(lz4f._xxh32(desc) >> 8) & 0xFF])
    frame += struct.pack('<I', len(block)) + block + b'\0\0\0\0'
    assert lz4f.decode(frame)[0] == b'abababab!'


def test_content_checksum_is_checked():
    frame = bytearray(lz4f.encode(b'hello'))
    frame[-1] ^= 1
    with pytest.raises(ValueError):
        lz4f.decode(bytes(frame))
