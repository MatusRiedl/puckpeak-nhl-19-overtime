"""The app's Update (check, apply, undo), driven through the Controller the way the page does (jobs run inline; NHL.com
and the data pack are replaced by the recorded 2026-27 fixtures). The calendar it brings: test_calendar_app.py."""
import json
import os

import pytest

from overtime_roster.app import controller as C, jobs, sources, update

DATA = os.path.join(os.path.dirname(__file__), 'data')


class Host:
    def __init__(self):
        self.snaps, self.lines = {}, []

    def register(self, name, fn):
        self.snaps[name] = fn

    def changed(self, *names):
        pass

    def log(self, msg):
        self.lines.append(msg)

    def send(self, *a):
        pass

    def open_path(self, path):
        pass

    def snap(self, name):
        return self.snaps[name]()


def fixtures():
    with open(os.path.join(DATA, 'nhl_rosters_20262027.json'), encoding='utf-8') as f:
        real = json.load(f)
    with open(os.path.join(DATA, 'nhl_schedule_20262027.json'), encoding='utf-8') as f:
        games = [tuple(g) for g in json.load(f)]
    return real, games


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
    real, games = fixtures()
    rating = [{'name': 'Leo Carlsson', 'position': 'C', 'birth': [2004, 12, 26], 'attrs': {'Passing': 90}}]

    def gather(client, season, pack_dir, fetch=None, offline=False, step=None, log=None):
        for k in update.GATHER_STEPS:
            step(k, 'ok', 'fixture')
        return update.Gathered(season, real, games, rating, [], {'rosters': 'fixture', 'calendar': 'fixture'})
    monkeypatch.setattr(update, 'gather', gather)
    host = Host()
    c = C.Controller(host, game_dir=game_dir, save_dir=str(tmp_path / 'saves'))
    c.load_source(sources.GAME_ID)
    assert c.session is not None
    return c, host


@pytest.mark.game
def test_update_check_apply_undo(app):
    c, host = app
    before = c.session.db.to_bytes()
    assert c.snap_update()['can_apply'] is False
    assert c.update_check() is None
    u = c.snap_update()
    assert u['plan']['summary']['players'] == 772 and u['can_apply']
    assert {s['key']: s['state'] for s in u['steps']}['plan'] == 'ok'

    c.update_apply()
    u = c.snap_update()
    steps = {s['key']: s['state'] for s in u['steps']}
    assert steps['apply'] == 'ok' and steps['verify'] == 'ok', host.lines[-20:]
    assert u['report']['problems'] == []
    save = c.snap_save()
    assert save['edit_count'] > 700 and save['verify']['errors'] == 0
    assert any(t['abbr'] == 'SEA' for t in c.snap_strategy()['teams'])

    for name in host.snaps:  # every slice goes to the page as JSON, and beta1's snapshots still work
        json.dumps(host.snap(name))
    for name in ('source', 'editor', 'lines', 'save', 'update', 'strategy', 'calendar', 'patch', 'status'):
        json.dumps(getattr(c, f'snap_{name}')())

    c.undo()
    assert c.session.db.to_bytes() == before and c.snap_update()['report'] is None
