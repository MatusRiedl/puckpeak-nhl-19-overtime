"""The game's roster CRC string: the value NHL_ROSTER `roster_h2h_crc` must hold (docs/notes/roster-download.md).

54 characters: nine u32 CRC-32/MPEG-2 values, each as 6 base-62 digits (0-9A-Za-z, most significant first).
Value 0 is one running CRC over every table of the roster savegroup, in the game's order for that group (the order
of the given database's tables); values 1..8 cover one table each (TABLES).

A table adds nothing unless its header +0x04 has bit 0x2 and it holds records. Otherwise it adds the CRCs of the
bytes of its first `count` records, sorted ascending, each as a u32 little-endian. A record whose last bit is set is
skipped (the game's deleted flag; no field covers that bit). Compressed-string fields would be replaced by the CRC
of their string first; roster tables have none, so they are rejected here.
"""
import struct

from .crc import crc32_mpeg2
from .tdb import TYPE_HUFF8, TYPE_HUFF16

ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
# Table enums 26, 27, 29, 30, 34, 35, 39, 100 (the alphabetical order of the 111 table names): exhibitionfreeagents,
# exhibitiongoalieai, exhibitionplayerbiotable, exhibitionplayers, exhibitionrostertable, exhibitionskaterai,
# favoriteteamschedule, stockteamjerseys.
TABLES = ('VoEQ', 'mHuy', 'ubPc', 'ZBac', 'eGlu', 'dSvy', 'qiwI', 'xjgw')
LENGTH = 6 * (1 + len(TABLES))


def base62(value):
    out = ''
    for _ in range(6):
        value, digit = divmod(value, 62)
        out = ALPHABET[digit] + out
    return out


def table_crc(table, crc=0xFFFFFFFF):
    """Continue `crc` over one table's live records."""
    if any(f.type in (TYPE_HUFF8, TYPE_HUFF16, 15) for f in table.fields):
        raise ValueError(f"{table.name}: compressed-string fields are not supported")
    if not table._header[4] & 0x2 or table.count == 0:
        return crc
    n = table.record_length
    last = struct.unpack_from('<I', table._header, 0x0C)[0]  # record length in bits - 1
    recs = []
    for row in range(table.count):
        rec = table.data[row * n:(row + 1) * n]
        if rec[last >> 3] >> (last & 7) & 1:
            continue
        recs.append(crc32_mpeg2(rec))
    recs.sort()
    return crc32_mpeg2(b''.join(struct.pack('<I', c) for c in recs), crc)


def roster_crc(db):
    """The 54-character string for `db`, a database holding the roster savegroup's tables in the game's order."""
    crc = 0xFFFFFFFF
    for t in db.tables:
        crc = table_crc(t, crc)
    return base62(crc) + ''.join(base62(table_crc(db[tag])) for tag in TABLES)
