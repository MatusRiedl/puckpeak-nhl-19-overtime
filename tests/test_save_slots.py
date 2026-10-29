"""The game lists only RosterCustom0-14: a 16th custom roster is refused with a clear message and one of the 15 can be
overwritten instead (after the backup); roster keys out of the stock layout (they crash Play Now) are put right on the
way, and a roster whose keys cannot be put right is never written."""
import os

import pytest

from overtime_core import rosterupdate as U, savefile, sfo
from overtime_roster.app import install, savegame, sources
from overtime_roster.app.session import RosterSession


def _sfo():
    return sfo.build([sfo.Entry('ACCOUNT_ID', sfo.FMT_BYTES, b'\x01' * 8, 8),
                      sfo.Entry('MAINTITLE', sfo.FMT_UTF8, 'Official Roster', 128),
                      sfo.Entry('SUBTITLE', sfo.FMT_UTF8, '', 128),
                      sfo.Entry('SAVEDATA_DIRECTORY', sfo.FMT_UTF8, 'RosterOnline0', 32),
                      sfo.Entry('SAVEDATA_LIST_PARAM', sfo.FMT_U32, 0, 4)])


def _template_save(dst):
    os.makedirs(os.path.join(dst, 'Profile0', 'sce_sys'))
    with open(os.path.join(dst, 'Profile0', 'sce_sys', 'param.sfo'), 'wb') as f:
        f.write(_sfo())
    index, data = savefile.build([savefile.SaveEntry('Profile0', bytes(8), savefile.pack(b'{}'))])
    for n, b in (('INDEX', index), ('DATA', data)):
        with open(os.path.join(dst, 'Profile0', n), 'wb') as f:
            f.write(b)


def _fill(saves, names):
    for n in names:
        os.makedirs(os.path.join(saves, n))
        with open(os.path.join(saves, n, 'DATA'), 'wb') as f:
            f.write(n.encode())


def test_next_free_name_stops_at_the_fifteen_slots(tmp_path):
    assert savegame.slot_names()[-1] == 'RosterCustom14' and len(savegame.slot_names()) == 15
    _fill(tmp_path, [f'RosterCustom{n}' for n in range(14)])
    assert savegame.next_free_name(str(tmp_path)) == 'RosterCustom14'
    _fill(tmp_path, ['RosterCustom14'])
    with pytest.raises(savegame.SaveError, match='only 15 custom rosters'):
        savegame.next_free_name(str(tmp_path))
    os.rename(tmp_path / 'RosterCustom3', tmp_path / 'gone')
    assert savegame.next_free_name(str(tmp_path)) == 'RosterCustom3'          # a gap is reused
    assert savegame.next_free_name(str(tmp_path), 'Other') == 'Other0'         # other prefixes have no limit
    assert savegame.used_slots(str(tmp_path)) == [f'RosterCustom{n}' for n in range(15) if n != 3]


def test_replace_swaps_a_slot_and_nothing_else(tmp_path):
    _fill(tmp_path, ['RosterCustom0', 'RosterCustom1'])
    path = savegame.write_new_folder(str(tmp_path), 'RosterCustom1', b'i', b'new', _sfo(), replace=True)
    assert (tmp_path / 'RosterCustom1' / 'DATA').read_bytes() == b'new' and path.endswith('RosterCustom1')
    assert (tmp_path / 'RosterCustom0' / 'DATA').read_bytes() == b'RosterCustom0'
    assert sorted(os.listdir(tmp_path)) == ['RosterCustom0', 'RosterCustom1']   # nothing left aside
    with pytest.raises(savegame.SaveError):
        savegame.write_new_folder(str(tmp_path), 'RosterCustom5', b'i', b'd', _sfo(), replace=True)   # not there
    with pytest.raises(savegame.SaveError):
        savegame.write_new_folder(str(tmp_path), 'Profile0', b'i', b'd', _sfo(), replace=True)        # not a slot
    with pytest.raises(savegame.SaveError):
        savegame.write_new_folder(str(tmp_path), 'RosterCustom0', b'i', b'd', _sfo())                 # no replace


@pytest.fixture(scope='module')
def game(game_dir):
    return sources.GameData(game_dir)


@pytest.fixture
def session(game):
    return RosterSession(game.default_db(), 'NHL 19 default roster')


@pytest.mark.game
def test_pipeline_refuses_a_sixteenth_then_overwrites(session, game, tmp_path):
    saves = tmp_path / 'saves'
    _template_save(str(saves))
    _fill(saves, savegame.slot_names())
    out = install.run(session, game, install.TARGET_SAVE, 'Full', str(saves), str(tmp_path / 'home' / 'exports'),
                      log=lambda *a: None)
    assert not out.ok and 'only 15 custom rosters' in out.lines[0]
    assert sorted(os.listdir(saves)) == sorted(['Profile0'] + savegame.slot_names())
    out = install.run(session, game, install.TARGET_SAVE, 'Swap', str(saves), str(tmp_path / 'home' / 'exports'),
                      log=lambda *a: None, overwrite='RosterCustom7')
    assert out.ok, out.lines
    assert savegame.read(out.folder).meta['FileDisplayName'] == 'Swap' and 'replacing' in out.lines[0]
    assert (saves / 'RosterCustom6' / 'DATA').read_bytes() == b'RosterCustom6'
    backups = tmp_path / 'home' / 'backups'
    (stamp,) = os.listdir(backups)
    assert (backups / stamp / 'RosterCustom7' / 'DATA').read_bytes() == b'RosterCustom7'   # the old one is kept
    out = install.run(session, game, install.TARGET_SAVE, 'No', str(saves), str(tmp_path / 'x'),
                      log=lambda *a: None, overwrite='Profile0')
    assert not out.ok


@pytest.mark.game
def test_pipeline_puts_roster_keys_right(session, game, tmp_path):
    saves = tmp_path / 'saves'
    _template_save(str(saves))
    t = session.db[U.ROSTER]
    t.set(3, 'key', t.get(3, 'key') + 7)
    assert U.key_problems(session.db)
    lines = []
    out = install.run(session, game, install.TARGET_SAVE, 'Bad keys', str(saves), str(tmp_path / 'exports'),
                      log=lines.append)
    assert out.ok, out.lines
    assert any('Roster keys put in the order' in x for x in lines)
    from overtime_core import rostercrc, tdb
    written = tdb.Database.parse(savegame.read(out.folder).db_bytes, game.schema())
    assert U.key_problems(written) == []
    order = install.group_order(game.schema(), 'rosterupdate')
    assert savegame.read(out.folder).meta['CRCValue'] == rostercrc.roster_crc(
        tdb.Database([written[n] for n in order], written._header))     # the CRC of the keys written


@pytest.mark.game
def test_pipeline_refuses_keys_it_cannot_put_right(session, game, tmp_path):
    saves = tmp_path / 'saves'
    _template_save(str(saves))
    t = session.db[U.ROSTER]
    first, last = t.get(0, 'team'), t.get(t.count - 1, 'team')
    t.set(t.count - 1, 'team', first)               # one of the last team's players sits apart from his team
    t.set(t.count - 1, 'key', 0)
    assert first != last and U.key_problems(session.db)
    out = install.run(session, game, install.TARGET_SAVE, 'Split', str(saves), str(tmp_path / 'exports'),
                      log=lambda *a: None)
    assert not out.ok and 'not together' in out.lines[0]
    assert sorted(os.listdir(saves)) == ['Profile0']


def test_prune_backups_keeps_the_newest_ten(tmp_path):
    names = [f'2026{m:02d}{d:02d}-120000' for m in (9, 10) for d in range(1, 8)]     # 14 stamps, oldest first
    for n in names:
        (tmp_path / n).mkdir()
        (tmp_path / n / 'RosterCustom0').mkdir()
    (tmp_path / 'notes').mkdir()                          # not a backup: left alone
    (tmp_path / '20260101-000000.txt').write_text('x')    # a file, not a folder
    assert savegame.prune_backups(str(tmp_path)) == names[:4]
    left = sorted(os.listdir(tmp_path))
    assert left == sorted(names[4:] + ['notes', '20260101-000000.txt'])
    assert savegame.prune_backups(str(tmp_path)) == []
    assert savegame.prune_backups(str(tmp_path / 'missing')) == []
