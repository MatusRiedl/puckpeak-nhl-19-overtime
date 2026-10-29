"""Minimal LZ4 frame format codec (decode fully; encode with stored blocks or a simple greedy matcher).

Spec: https://github.com/lz4/lz4/blob/dev/doc/lz4_Frame_format.md and lz4_Block_format.md
"""
import struct

MAGIC = 0x184D2204


def _xxh32(data, seed=0):
    p1, p2, p3, p4, p5 = 2654435761, 2246822519, 3266489917, 668265263, 374761393
    m = 0xFFFFFFFF
    rotl = lambda x, r: ((x << r) | (x >> (32 - r))) & m
    n, i = len(data), 0
    if n >= 16:
        v = [(seed + p1 + p2) & m, (seed + p2) & m, seed & m, (seed - p1) & m]
        while i <= n - 16:
            for k in range(4):
                v[k] = (rotl((v[k] + struct.unpack_from('<I', data, i)[0] * p2) & m, 13) * p1) & m
                i += 4
        h = (rotl(v[0], 1) + rotl(v[1], 7) + rotl(v[2], 12) + rotl(v[3], 18)) & m
    else:
        h = (seed + p5) & m
    h = (h + n) & m
    while i <= n - 4:
        h = (rotl((h + struct.unpack_from('<I', data, i)[0] * p3) & m, 17) * p4) & m
        i += 4
    while i < n:
        h = (rotl((h + data[i] * p5) & m, 11) * p1) & m
        i += 1
    h ^= h >> 15
    h = (h * p2) & m
    h ^= h >> 13
    h = (h * p3) & m
    return h ^ (h >> 16)


def block_decode(src, out, limit=None):
    """Decode one block onto `out`; with `limit`, stop once `out` holds at least that many bytes."""
    i, n = 0, len(src)
    while i < n and (limit is None or len(out) < limit):
        tok = src[i]; i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1; lit += b
                if b != 255:
                    break
        out += src[i:i + lit]; i += lit
        if i >= n:
            break
        off = src[i] | src[i + 1] << 8; i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]; i += 1; ml += b
                if b != 255:
                    break
        ml += 4
        start = len(out) - off
        for k in range(ml):  # byte-wise: matches may overlap
            out.append(out[start + k])
    return out


def decode(data):
    """Decode one LZ4 frame. Returns (bytes, frame length)."""
    if struct.unpack_from('<I', data, 0)[0] != MAGIC:
        raise ValueError('not an LZ4 frame')
    flg, bd = data[4], data[5]
    pos = 6
    content_size = None
    if flg & 0x08:
        content_size = struct.unpack_from('<Q', data, pos)[0]; pos += 8
    if flg & 0x01:
        pos += 4  # dictionary id
    pos += 1  # header checksum
    out = bytearray()
    while True:
        bsize = struct.unpack_from('<I', data, pos)[0]; pos += 4
        if bsize == 0:
            break
        raw, bsize = bsize & 0x80000000, bsize & 0x7FFFFFFF
        block = data[pos:pos + bsize]; pos += bsize
        if raw:
            out += block
        else:
            block_decode(block, out)
        if flg & 0x10:
            pos += 4  # block checksum
    if flg & 0x04:
        if struct.unpack_from('<I', data, pos)[0] != _xxh32(bytes(out)):
            raise ValueError('LZ4 content checksum mismatch')
        pos += 4
    if content_size is not None and content_size != len(out):
        raise ValueError('LZ4 content size mismatch')
    return bytes(out), pos


def decode_prefix(data, size):
    """The first `size` bytes of one LZ4 frame's content (fewer when it is shorter), decoding only as far as needed:
    no checksum is checked (a full decode does that)."""
    if struct.unpack_from('<I', data, 0)[0] != MAGIC:
        raise ValueError('not an LZ4 frame')
    flg = data[4]
    pos = 6 + (8 if flg & 0x08 else 0) + (4 if flg & 0x01 else 0) + 1
    out = bytearray()
    while len(out) < size:
        bsize = struct.unpack_from('<I', data, pos)[0]; pos += 4
        if bsize == 0:
            break
        raw, bsize = bsize & 0x80000000, bsize & 0x7FFFFFFF
        block = data[pos:pos + bsize]; pos += bsize
        if raw:
            out += block
        else:
            block_decode(block, out, size)
        if flg & 0x10:
            pos += 4
    return bytes(out[:size])


def encode(data, content_checksum=True, block_max=4 << 20):
    """Encode as one LZ4 frame with stored (uncompressed) blocks. Valid for any compliant decoder."""
    bd_code = {64 << 10: 4, 256 << 10: 5, 1 << 20: 6, 4 << 20: 7}[block_max]
    flg = 0x40 | 0x20 | (0x04 if content_checksum else 0)  # version 01, block independence
    desc = bytes([flg, bd_code << 4])
    out = bytearray(struct.pack('<I', MAGIC)) + desc + bytes([(_xxh32(desc) >> 8) & 0xFF])
    for i in range(0, len(data), block_max):
        chunk = data[i:i + block_max]
        out += struct.pack('<I', len(chunk) | 0x80000000) + chunk
    out += b'\0\0\0\0'
    if content_checksum:
        out += struct.pack('<I', _xxh32(bytes(data)))
    return bytes(out)


def _emit(out, lit, offset=0, ml=0):
    """One LZ4 sequence: literals, then (when ml) a match of ml bytes at `offset` back."""
    ll = len(lit)
    m = ml - 4 if ml else 0
    out.append((min(ll, 15) << 4) | (min(m, 15) if ml else 0))
    if ll >= 15:
        r = ll - 15
        while r >= 255:
            out.append(255)
            r -= 255
        out.append(r)
    out += lit
    if ml:
        out += struct.pack('<H', offset)
        if m >= 15:
            r = m - 15
            while r >= 255:
                out.append(255)
                r -= 255
            out.append(r)


def compress_block(src):
    """Greedy LZ4 block compression (no dictionary, matches inside `src` only)."""
    src = bytes(src)
    n = len(src)
    out = bytearray()
    anchor = i = 0
    table = {}
    limit, mflimit = n - 12, n - 5  # format rules: last match starts 12+ and ends 5+ bytes before the end
    while i < limit:
        key = src[i:i + 4]
        j = table.get(key)
        table[key] = i
        if j is None or i - j > 0xFFFF:
            i += 1 + ((i - anchor) >> 7)  # skip faster through data that does not compress
            continue
        ml, maxml = 4, mflimit - i
        while ml + 64 <= maxml and src[i + ml:i + ml + 64] == src[j + ml:j + ml + 64]:
            ml += 64
        while ml < maxml and src[i + ml] == src[j + ml]:
            ml += 1
        _emit(out, src[anchor:i], i - j, ml)
        i += ml
        anchor = i
    _emit(out, src[anchor:])
    return bytes(out)


def encode_compressed(data, content_checksum=True, block_max=64 << 10):
    """One LZ4 frame with independently compressed blocks (stored when compression does not help), as the
    game writes its saves (FLG 0x64, 64 KB blocks)."""
    bd_code = {64 << 10: 4, 256 << 10: 5, 1 << 20: 6, 4 << 20: 7}[block_max]
    flg = 0x40 | 0x20 | (0x04 if content_checksum else 0)
    desc = bytes([flg, bd_code << 4])
    out = bytearray(struct.pack('<I', MAGIC)) + desc + bytes([(_xxh32(desc) >> 8) & 0xFF])
    for k in range(0, len(data), block_max):
        chunk = bytes(data[k:k + block_max])
        packed = compress_block(chunk)
        if len(packed) < len(chunk):
            out += struct.pack('<I', len(packed)) + packed
        else:
            out += struct.pack('<I', len(chunk) | 0x80000000) + chunk
    out += b'\0\0\0\0'
    if content_checksum:
        out += struct.pack('<I', _xxh32(bytes(data)))
    return bytes(out)
