import os
import shutil
import struct

import pytest

from overtime_core import eb, gamefiles, textpack


def make_eb(path, files):
    """Minimal EB v3 archive: `files` = [(folder, name, data)], one folder table, 16-byte aligned data."""
    folders = sorted({f for f, _, _ in files})
    fnl, dnl = 32, 64
    names = b''.join(struct.pack('>H', folders.index(f)) + n.encode().ljust(fnl - 2, b'\0') for f, n, _ in files)
    names = names.ljust((len(names) + 15) // 16 * 16, b'\0') + b''.join(f.encode().ljust(dnl, b'\0') for f in folders)
    names_off = (0x30 + 20 * len(files) + 15) // 16 * 16
    pos = (names_off + len(names) + 15) // 16 * 16
    table, blobs = b'', b''
    for _, _, data in files:
        table += struct.pack('>IIIQ', pos // 16, 0, len(data), 0)
        blob = data.ljust((len(data) + 15) // 16 * 16, b'\0')
        blobs += blob
        pos += len(blob)
    head = b'EB' + struct.pack('>HIIIIBBHII', 3, len(files), 0, names_off, len(names), fnl, dnl, len(folders), 0, pos)
    body = head.ljust(0x30, b'\0') + table
    body = body.ljust(names_off, b'\0') + names
    body = body.ljust((len(body) + 15) // 16 * 16, b'\0') + blobs
    with open(path, 'wb') as f:
        f.write(body)
    return body


def test_append_and_restore_entry(tmp_path):
    p = str(tmp_path / 'a.big')
    original = make_eb(p, [('x/y', 'one.db', b'first'), ('x/y', 'two.db', b'second!')])
    rec = eb.append_entry(p, 'x/y/one.db', b'replaced and longer')
    with eb.EbArchive(p) as arc:
        assert arc.read('x/y/one.db') == b'replaced and longer'
        assert arc.read('x/y/two.db') == b'second!'
    size = os.path.getsize(p)
    with open(p, 'rb') as f:
        assert struct.unpack_from('>I', f.read(0x30), 0x1c)[0] == size and size % 16 == 0
    eb.restore_entry(p, rec)
    with open(p, 'rb') as f:
        assert f.read() == original


def test_append_refuses_mismatched_header(tmp_path):
    p = str(tmp_path / 'a.big')
    make_eb(p, [('d', 'f', b'abc')])
    with open(p, 'ab') as f:
        f.write(b'\0' * 16)
    with pytest.raises(ValueError):
        eb.append_entry(p, 'd/f', b'x')


def test_pack_strings_fit_their_field():
    pack = textpack.load_pack()
    for sid, text in pack['strings'].items():
        assert len(text.encode('utf-8')) <= 32000 // 8, sid


@pytest.mark.game
def test_apply_and_undo_on_a_copy(game_dir, tmp_path):
    db_path, _ = textpack.loc_paths('eng_us')
    src = textpack._winner(game_dir, db_path)
    game = tmp_path / 'game'
    (game / 'databigs').mkdir(parents=True)
    copy = str(game / 'databigs' / os.path.basename(src))
    shutil.copyfile(src, copy)
    meta_path = textpack.loc_paths('eng_us')[1]
    folder, name = meta_path.rsplit('/', 1)
    make_eb(str(game / 'databigs' / 'inxp_00.big'), [(folder, name, gamefiles.read_latest(game_dir, meta_path)[0])])
    if os.path.exists(src + textpack.STATE_SUFFIX):  # an old in-place edit: the overlay starts from the original
        shutil.copyfile(src + textpack.STATE_SUFFIX, copy + textpack.STATE_SUFFIX)
    before = open(copy, 'rb').read()
    pack = textpack.load_pack()
    idle = {'running': lambda: False}  # the overlay is never written while shadPS4 runs
    out = textpack.apply(str(game), pack, **idle)
    assert out['overlay'] == str(tmp_path / 'game-mods' / 'databigs' / os.path.basename(src))
    size = os.path.getsize(out['overlay'])
    textpack.apply(str(game), pack, **idle)
    assert os.path.getsize(out['overlay']) == size
    assert open(copy, 'rb').read() == before  # the game folder is never written
    st = textpack.status(str(game), pack)
    assert st['applied'] and st['not_current'] == []
    in_place = os.path.exists(copy + textpack.STATE_SUFFIX)
    textpack.undo(str(game), **idle)
    assert not os.path.exists(out['overlay'])
    assert in_place or textpack.status(str(game), pack)['not_current']
