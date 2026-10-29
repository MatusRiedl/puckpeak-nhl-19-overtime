"""The Source tab lists roster saves from their metadata and database header (savegame.peek), cached on the
INDEX/DATA size and mtime; the roster is unpacked only when opened."""
import os
import struct

import pytest

from overtime_core import lz4f, savefile
from overtime_roster.app import savegame, sources


def _db(size, fill=b'\x5a'):
    return b'DB\x00\x08' + b'\0' * 4 + struct.pack('<I', size) + fill * (size - 12)


def _write(save_dir, name, db, meta=None, stored=False):
    folder = os.path.join(save_dir, name)
    os.makedirs(folder, exist_ok=True)
    meta = meta or {'FileDisplayName': 'My roster', 'FileModifiedDate': '1760000000', 'CRCValue': '42'}
    if stored:      # stored LZ4 blocks with a content checksum: a flipped byte breaks only the checksum
        stamp = b'\0' * 8
        files = [savefile.SaveEntry('__SaveLoadMetaData', stamp, savegame.meta_json(meta)),
                 savefile.SaveEntry(name, stamp, savefile.pack(db + savegame.trailer_for(len(db))))]
        index, data = savefile.build(files)
    else:
        index, data = savegame.build_container(name, db, meta)
    with open(os.path.join(folder, 'INDEX'), 'wb') as f:
        f.write(index)
    with open(os.path.join(folder, 'DATA'), 'wb') as f:
        f.write(data)
    return folder


class NoGame:
    ok, game_dir = False, 'nowhere'


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(sources, '_LISTED', {})


def test_decode_prefix_matches_a_full_decode():
    data = bytes(range(256)) * 300 + b'tail' * 1000
    frame = lz4f.encode_compressed(data)
    for n in (0, 12, 1000, len(data), len(data) + 10):
        assert lz4f.decode_prefix(frame, n) == data[:n]
    assert lz4f.decode_prefix(lz4f.encode(data), 12) == data[:12]


def test_peek_gives_what_a_full_read_gives(tmp_path):
    folder = _write(str(tmp_path), 'RosterCustom3', _db(150_000))
    full, quick = savegame.read(folder), savegame.peek(folder)
    assert quick.db_size == len(full.db_bytes) == 150_000 and quick.meta == full.meta and quick.name == full.name


def test_listing_is_cached_on_size_and_mtime(tmp_path, monkeypatch):
    save_dir = str(tmp_path)
    folder = _write(save_dir, 'RosterCustom0', _db(40_000))
    peeked = []
    real = savegame.peek
    monkeypatch.setattr(savegame, 'peek', lambda f: peeked.append(f) or real(f))
    first = sources.find(NoGame(), save_dir)
    assert [s.view() for s in sources.find(NoGame(), save_dir)] == [s.view() for s in first]
    assert peeked == [folder]
    key = sources.listing_key(folder)
    assert key == sources.listing_key(folder) and None not in key
    # the same size, another mtime: read again
    st = os.stat(os.path.join(folder, 'DATA'))
    os.utime(os.path.join(folder, 'DATA'), ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    sources.find(NoGame(), save_dir)
    assert len(peeked) == 2
    # rewritten with another roster (another size): read again, and the listing shows it
    _write(save_dir, 'RosterCustom0', _db(90_000), meta={'FileDisplayName': 'Newer'})
    save = sources.find(NoGame(), save_dir)[1]
    assert len(peeked) == 3 and save.name == 'Newer' and '87 KB' in save.meta


def test_listing_matches_the_old_full_read(tmp_path):
    folder = _write(str(tmp_path), 'RosterOnline0', _db(70_000))
    save = sources.find(NoGame(), str(tmp_path))[1]
    rs = savegame.read(folder)
    assert save.usable and save.name == 'My roster' and save.info == {'crc': '42', 'folder': 'RosterOnline0'}
    assert save.meta.startswith('RosterOnline0 · online roster · ') and save.meta.endswith(
        f'{len(rs.db_bytes) // 1024} KB')


def test_a_broken_header_is_listed_as_unusable(tmp_path):
    _write(str(tmp_path), 'RosterCustom1', b'XXXX' + _db(20_000)[4:])
    save = sources.find(NoGame(), str(tmp_path))[1]
    assert not save.usable and save.problem.startswith('Cannot read:')


def test_damage_past_the_header_shows_when_the_save_is_opened(tmp_path):
    folder = _write(str(tmp_path), 'RosterCustom2', _db(20_000, fill=b'\x33'), stored=True)
    path = os.path.join(folder, 'DATA')
    data = bytearray(open(path, 'rb').read())
    data[data.rindex(b'\x33')] = 0x34
    open(path, 'wb').write(bytes(data))
    save = sources.find(NoGame(), str(tmp_path))[1]
    assert save.usable                  # listed from its header ...
    with pytest.raises(ValueError):     # ... and refused when opened (the full read checks the LZ4 checksum)
        sources.load(save, NoGame())


def test_a_listed_source_is_a_copy(tmp_path):
    _write(str(tmp_path), 'RosterCustom4', _db(20_000))
    sources.find(NoGame(), str(tmp_path))[1].info['crc'] = 'changed'
    assert sources.find(NoGame(), str(tmp_path))[1].info['crc'] == '42'
