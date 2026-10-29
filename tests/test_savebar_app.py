"""The Save bar (app/save_ctl.py) through the Controller the way the page drives it, on the game's roster and a
throwaway saves folder: My edits carry their tab and team, the rail shows the dot, Save as new opens the new save
(the bar then updates it), Ctrl+S's rules (nothing to save, no name) and a saved change taken back."""
import os

import pytest

from overtime_core import savefile, sfo
from overtime_roster.app import controller as C, jobs, savegame, sources

TEAM = 11


class Host:
    def __init__(self):
        self.snaps, self.lines = {}, []

    def register(self, name, fn):
        self.snaps[name] = fn

    def changed(self, *names):
        pass

    def log(self, *lines):
        self.lines.extend(lines)

    def send(self, *a):
        pass

    def open_path(self, path):
        pass

    def snap(self, name):
        return self.snaps[name]()


def _template_save(dst):
    """A save folder like the game's: Profile0 with a param.sfo, enough for the pipeline's template."""
    os.makedirs(os.path.join(dst, 'Profile0', 'sce_sys'))
    raw = sfo.build([sfo.Entry('ACCOUNT_ID', sfo.FMT_BYTES, b'\x01' * 8, 8),
                     sfo.Entry('MAINTITLE', sfo.FMT_UTF8, 'Official Roster', 128),
                     sfo.Entry('SAVEDATA_DIRECTORY', sfo.FMT_UTF8, 'RosterOnline0', 32),
                     sfo.Entry('SAVEDATA_LIST_PARAM', sfo.FMT_U32, 0, 4)])
    with open(os.path.join(dst, 'Profile0', 'sce_sys', 'param.sfo'), 'wb') as f:
        f.write(raw)
    index, data = savefile.build([savefile.SaveEntry('Profile0', bytes(8), savefile.pack(b'{}'))])
    for n, b in (('INDEX', index), ('DATA', data)):
        with open(os.path.join(dst, 'Profile0', n), 'wb') as f:
            f.write(b)


@pytest.fixture
def app(game_dir, tmp_path, monkeypatch):
    monkeypatch.setenv('OVERTIME_ROSTER_HOME', str(tmp_path / 'home'))

    def inline(work, done=None, failed=None, expected=()):
        try:
            out = work()
        except expected as err:
            return failed and failed(str(err))
        return done and done(out)
    monkeypatch.setattr(jobs, 'run', inline)
    saves = str(tmp_path / 'saves')
    _template_save(saves)
    c = C.Controller(Host(), game_dir=game_dir, save_dir=saves)
    c.load_source(sources.GAME_ID)
    c.calls['tab']('roster')
    c.calls['rail_team'](TEAM)
    return c, saves


def _edit(c, first):
    pi = c.session.players_of(TEAM)[0]
    c.calls['roster_player'](pi, None)
    assert c.calls['roster_apply']({'first': first}) == {'ok': True, 'changes': 1}


def _dots(c):
    return {r['id'] for r in c.host.snap('rail')['rows'] if r['dirty']}


@pytest.mark.game
def test_save_as_new_then_update_it(app):
    c, saves = app
    bar = c.host.snap('save')
    assert bar['roster']['kind'] == 'start' and bar['mode'] == 'new' and bar['button']['text'] == 'Save as new'
    _edit(c, 'Ryanx')
    c.calls['rail_team'](0)                                  # another team in view: the edit keeps its own
    bar = c.host.snap('save')
    code = c.rail.chip(TEAM)['code']
    assert bar['unsaved'] == 1 and [(e['tab'], e['team'], e['code']) for e in bar['edits']] == [('Roster', TEAM, code)]
    c.calls['rail_team'](TEAM)
    assert _dots(c) == {TEAM}

    c.calls['save_name']('My roster')
    assert c.calls['save'](None) is None
    assert sorted(savegame.used_slots(saves)) == ['RosterCustom0']
    assert c.parts['rosters'].open_id == 'save:RosterCustom0'      # the new save is the open roster now
    bar = c.host.snap('save')
    assert bar['roster'] == {'id': 'RosterCustom0', 'name': 'My roster', 'kind': 'save'}
    assert (bar['mode'], bar['name'], bar['unsaved']) == ('update', '', 0)
    assert bar['button'] == {'text': 'Save', 'enabled': False} and _dots(c) == set()
    assert c.calls['save'](None) == {'error': 'Nothing to save yet.'}       # Ctrl+S with the button off

    _edit(c, 'Ryany')
    assert c.calls['save'](None) is None                     # writes over the open save, no new folder
    assert sorted(savegame.used_slots(saves)) == ['RosterCustom0'] and c.host.snap('save')['unsaved'] == 0

    assert c.calls['roster_undo']('applied') == {'ok': False}   # the card takes back only what is not saved
    c.calls['undo']()                                        # a saved change taken back (the roster's Undo): unsaved again
    bar = c.host.snap('save')
    assert bar['unsaved'] == 1 and bar['edits'][0]['label'].startswith('Taken back: ') and _dots(c) == {TEAM}
    c.calls['save_mode']('new')
    assert c.calls['save'](None) == {'error': 'Type a name for the new roster first.'}
    assert c.status['text'] == 'Type a name for the new roster first.'
