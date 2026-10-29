"""The face, type and player gear editors driven through the Controller the way the pages do: each edit one Undo,
refused values leave the roster alone, and the edits go through the roster save path. The Team gear tab:
test_jerseys_app.py."""
import pytest

from overtime_core import equipment as EQ, faces as F, tdb
from overtime_roster.app import controller as C, install, jobs, sources
from overtime_roster.app.session import RosterSession

TEAM = 11


class Host:
    def __init__(self):
        self.snaps, self.lines, self.seen = {}, [], []

    def register(self, name, fn):
        self.snaps[name] = fn

    def changed(self, *names):
        self.seen.append(names)

    def log(self, msg):
        self.lines.append(msg)

    def send(self, *a):
        pass

    def snap(self, name):
        return self.snaps[name]()


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
    c = C.Controller(Host(), game_dir=game_dir, save_dir=str(tmp_path / 'saves'))
    c.load_source(sources.GAME_ID)
    c.pick_team(TEAM)
    return c, c.host


def _skaters(c):
    s = c.session
    return [p for p in s.players_of(TEAM) if s.bio(p)[1]['position'] != F.GOALIE]


@pytest.mark.game
def test_type_and_face_through_the_controller(app):
    c, host = app
    a, b = _skaters(c)[:2]
    c.pick_player(a)
    f = c.editors.snap_faces()
    assert f['ready'] and f['player'] == a and f['type_ok'] and len(f['types']) in (4, 6)
    assert any(names == ('faces',) or 'faces' in names for names in host.seen)   # follows the editor slice
    other = next(n for n, _ in f['types'] if n != f['type'])
    edits = len(c.session.history)
    assert c.editors.type_set(other) == {'ok': True}
    assert c.editors.snap_faces()['type'] == other and len(c.session.history) == edits + 1
    c.undo()
    assert c.editors.snap_faces()['type'] == f['type']
    assert c.editors.type_set(0).get('error')  # a goalie's type

    mate = F.read(c.session.bio(b)[1])
    assert c.editors.face_copy(b) == {'ok': True} and c.editors.snap_faces()['face'] == mate
    before = len(c.session.history)
    assert 'error' in c.editors.face_set({'head': 59999})
    assert 'error' in c.editors.face_set({'skin': 0})
    assert len(c.session.history) == before
    head = next(h for h in f['parts']['head'] if h != mate['head'])
    assert c.editors.face_set({'head': head, 'skin': 3}) == {'ok': True}
    got = c.editors.snap_faces()['face']
    assert got['head'] == head and got['skin'] == 3


@pytest.mark.game
def test_player_gear_and_team_wide(app):
    c, host = app
    a = _skaters(c)[0]
    c.pick_player(a)
    q = c.editors.snap_equipment()
    p = q['player']
    assert p and p['kind'] == 'skater' and {ch['key'] for ch in p['choices']} == set(EQ.SKATER)
    stick = next(n for n, _ in next(ch for ch in p['choices'] if ch['key'] == 'stick')['options'] if n != p['values']['stick'])
    assert c.editors.gear_set({'stick': stick, 'blade_tape': '#ff0000'}) == {'ok': True}
    v = c.editors.snap_equipment()['player']['values']
    assert v['stick'] == stick and v['blade_tape'] == '#ff0000'
    n = len(c.session.history)
    assert 'error' in c.editors.gear_set({'gloves': 4242}) and len(c.session.history) == n
    assert 'error' in c.editors.gear_set({'blade_tape': 'red'})
    assert c.editors.gear_team_wide('jersey_tuck') == {'ok': True}
    want = v['jersey_tuck']
    s = c.session
    for m in _skaters(c):
        row = EQ.row_of(s.db, F.Player(s.db, m).game_id)
        if row is not None:
            assert EQ.read(s.db, row)['jersey_tuck'] == want
    assert 'error' in c.editors.gear_team_wide('stick')


@pytest.mark.game
def test_editor_edits_round_trip_through_the_save(app):
    c, host = app
    s, game = c.session, c.game
    a, b = _skaters(c)[:2]
    c.pick_player(a)
    style = next(n for n, _ in c.editors.snap_faces()['types'] if n != c.editors.snap_faces()['type'])
    c.editors.type_set(style)
    c.editors.face_copy(b)
    c.editors.gear_set({'blade_tape': '#00ff00'})
    p = F.Player(s.db, a)
    want_face = F.read(s.bio(b)[1])
    for target in (install.TARGET_EXPORT, install.TARGET_SAVE):
        db = tdb.Database.parse(install.build_database(s, game, target).to_bytes(), game.schema())
        back = RosterSession(db)
        q = F.Player(db, a)
        assert db[q.ai_table].get(q.ai, F.STYLE) == style, target
        assert F.read(back.bio(a)[1]) == want_face, target
        assert EQ.read(db, EQ.row_of(db, p.game_id))['blade_tape'] == 0x00FF00, target
