"""PS4 `param.sfo` (PSF) files, as found in a save folder's `sce_sys/`.

Layout (little-endian): header 0x14 = magic `\\0PSF`, u32 version (0x101), u32 key table offset, u32 data table
offset, u32 entry count; then one 16-byte entry per key: u16 key offset, u16 format, u32 used length, u32 max
length, u32 data offset. Formats: 0x0004 raw bytes, 0x0204 UTF-8 with a NUL, 0x0404 u32.

Save folders written by NHL 19 hold ACCOUNT_ID, MAINTITLE, SUBTITLE, DETAIL, SAVEDATA_DIRECTORY,
SAVEDATA_LIST_PARAM, TITLE_ID and SAVEDATA_BLOCKS. `patch` rewrites values in place (same layout, same size), so a
copy of a real save's file can be relabelled for a new folder.
"""
import struct

MAGIC = b'\0PSF'
FMT_BYTES, FMT_UTF8, FMT_U32 = 0x0004, 0x0204, 0x0404


class SfoError(ValueError):
    pass


class Entry:
    def __init__(self, key, fmt, value, max_len):
        self.key, self.fmt, self.value, self.max_len = key, fmt, value, max_len

    def __repr__(self):
        return f"Entry({self.key!r}, {self.fmt:#06x}, {self.value!r})"


def _encode(e):
    if e.fmt == FMT_U32:
        return struct.pack('<I', e.value)
    if e.fmt == FMT_UTF8:
        return e.value.encode('utf-8') + b'\0'
    return bytes(e.value)


def parse(raw):
    """Entries of a param.sfo, in file order."""
    if raw[:4] != MAGIC:
        raise SfoError('not a param.sfo')
    _, keys, data, n = struct.unpack_from('<IIII', raw, 4)
    out = []
    for i in range(n):
        koff, fmt, used, max_len, doff = struct.unpack_from('<HHIII', raw, 0x14 + 16 * i)
        key = raw[keys + koff:raw.index(b'\0', keys + koff)].decode('ascii')
        blob = raw[data + doff:data + doff + used]
        if fmt == FMT_U32:
            value = struct.unpack('<I', blob)[0]
        elif fmt == FMT_UTF8:
            value = blob.split(b'\0', 1)[0].decode('utf-8')
        else:
            value = bytes(blob)
        out.append(Entry(key, fmt, value, max_len))
    return out


def build(entries, version=0x101):
    """A param.sfo holding `entries` (keys packed, values 4-aligned and padded to their max length,
    as in the files NHL 19 writes)."""
    keys = bytearray()
    koffs = []
    for e in entries:
        koffs.append(len(keys))
        keys += e.key.encode('ascii') + b'\0'
    key_start = 0x14 + 16 * len(entries)
    data_start = key_start + len(keys)
    table, data = bytearray(), bytearray(-data_start % 4)  # values start 4-aligned in the file
    for e, koff in zip(entries, koffs):
        blob = _encode(e)
        if len(blob) > e.max_len:
            raise SfoError(f"{e.key}: {len(blob)} bytes, max {e.max_len}")
        table += struct.pack('<HHIII', koff, e.fmt, len(blob), e.max_len, len(data))
        data += blob.ljust(e.max_len, b'\0')
    return MAGIC + struct.pack('<IIII', version, key_start, data_start, len(entries)) + bytes(table) + bytes(keys) + \
        bytes(data)


def patch(raw, values):
    """Return `raw` with the string / u32 values of the keys in `values` replaced in place.

    The layout is kept: each value must fit the key's max length. Unknown keys raise KeyError.
    """
    out = bytearray(raw)
    if raw[:4] != MAGIC:
        raise SfoError('not a param.sfo')
    _, keys, data, n = struct.unpack_from('<IIII', raw, 4)
    todo = dict(values)
    for i in range(n):
        at = 0x14 + 16 * i
        koff, fmt, used, max_len, doff = struct.unpack_from('<HHIII', raw, at)
        key = raw[keys + koff:raw.index(b'\0', keys + koff)].decode('ascii')
        if key not in todo:
            continue
        blob = _encode(Entry(key, fmt, todo.pop(key), max_len))
        if len(blob) > max_len:
            raise SfoError(f"{key}: {len(blob)} bytes, max {max_len}")
        out[data + doff:data + doff + max_len] = blob.ljust(max_len, b'\0')
        struct.pack_into('<I', out, at + 4, len(blob))
    if todo:
        raise KeyError(f"param.sfo has no {', '.join(sorted(todo))}")
    return bytes(out)


def values(raw):
    return {e.key: e.value for e in parse(raw)}
