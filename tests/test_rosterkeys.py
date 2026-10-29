"""Roster keys keep the stock layout key = 40 * team + n after the update (Play Now's match load crashed when a team's
keys ran into the next team's range)."""
import pytest

from overtime_core import rosterupdate as U, tdb
from tests.test_rosterupdate import real_rosters


@pytest.mark.game
def test_stock_keys_are_40_per_team(game_db):
    raw, schema = game_db
    assert U.key_problems(tdb.Database.parse(raw, schema)) == []


@pytest.mark.game
def test_update_keeps_the_stock_key_layout(game_db):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    U.apply(db, schema, U.plan(db, real_rosters()))
    assert U.key_problems(db) == []
    assert not [p for p in U.check(db, schema) if 'keys' in p]
    p = db[U.PLAYERS]
    records = {p.get(i, 'index') for i in range(p.count)}
    for table in (U.ROSTER, U.CUSTOM_ROSTER):
        t = db[table]
        keys = [t.get(i, 'key') for i in range(t.count)]
        assert len(set(keys)) == len(keys) and all(k // U.KEYS_PER_TEAM == t.get(i, 'team') for i, k in enumerate(keys))
        assert {t.get(i, 'playerindex') for i in range(t.count)} <= records  # the line slots are columns of the row


@pytest.mark.game
def test_rebuild_moves_rows_without_spilling_keys(game_db):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    t = db[U.ROSTER]
    first = [t.row(i) for i in range(t.count) if t.get(i, 'team') == 1]
    gone = {r['playerindex'] for r in first[:3]}
    adds = [(2, {k: v for k, v in r.items() if k != 'key'} | {'team': 2}) for r in first[:3]]
    U._rebuild_roster(t, gone, adds)
    keys = {team: [t.get(i, 'key') for i in range(t.count) if t.get(i, 'team') == team] for team in (1, 2)}
    assert keys[1] == list(range(40, 40 + len(first) - 3))
    assert keys[2] == list(range(80, 80 + len(keys[2]))) and len(keys[2]) == 27
    assert U.key_problems(db) == []


def test_rebuild_refuses_a_41st_row():
    class Col:
        depth = 15

    class Table:
        name, record_length, max_records = 'exhibitionrostertable', 4, 100
        by_name = {'key': Col}

        def __init__(self):
            self.data, self.count, self.cells = bytearray(400), 0, {}

        def get(self, i, name):
            return self.cells.get((i, name), 0)

        def set(self, i, name, value):
            self.cells[i, name] = value

    t = Table()
    with pytest.raises(U.UpdateError):
        U._rebuild_roster(t, set(), [(5, {'team': 5, 'playerindex': n}) for n in range(41)])
