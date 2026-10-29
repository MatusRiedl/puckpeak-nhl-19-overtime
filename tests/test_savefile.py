import os
import struct

import pytest

from overtime_core import savefile


def entries():
    return [savefile.SaveEntry('__SaveLoadFileInfo', b'\x01' * 8, b'{\n"IsBackup":false\n}'),
            savefile.SaveEntry('Profile0', b'\x02' * 8, savefile.pack(b'{"Roster":{}}' + bytes(70000)))]


def test_build_parse_roundtrip():
    index, data = savefile.build(entries())
    out = savefile.parse(index, data)
    assert [(e.name, e.stamp, e.payload) for e in out] == [(e.name, e.stamp, e.payload) for e in entries()]
    assert savefile.unpack(out[1].payload) == b'{"Roster":{}}' + bytes(70000)


def test_parse_file_split_over_two_extents():
    rec = struct.pack('<Q', 6) + b'S' * 8 + b'abcdef'
    data = rec[:10] + b'XXXX' + rec[10:]
    index = b'Profile0'.ljust(32, b'\0') + struct.pack('<QQ', 2, len(rec))
    index += struct.pack('<QQ', 0, 10) + bytes(16) + struct.pack('<QQ', 14, len(data)) + bytes(16)
    (e,) = savefile.parse(index, data)
    assert e.payload == b'abcdef' and e.stamp == b'S' * 8


def test_size_mismatch_rejected():
    index, data = savefile.build(entries())
    with pytest.raises(savefile.SaveFormatError):
        savefile.parse(index, data[:-1])


@pytest.mark.game
def test_real_profile_reads(game_dir):
    from conftest import SAVE_DIR
    folder = os.path.join(SAVE_DIR, 'Profile0')
    if not os.path.isfile(os.path.join(folder, 'INDEX')):
        pytest.skip('no Profile0 save')
    es = savefile.read_folder(folder)
    prof = next(e for e in es if e.name == 'Profile0')
    assert savefile.unpack(prof.payload).startswith(b'{')
    again = savefile.parse(*savefile.build(es))
    assert [e.payload for e in again] == [e.payload for e in es]
