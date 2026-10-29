"""Every NHL goalie has a career season row after the roster update, as in the stock roster."""
import pytest

from overtime_core import careerstats as S, rosterupdate as U, tdb
from tests.test_rosterupdate import real_rosters


@pytest.fixture(scope='module')
def updated(game_db):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    report = U.apply(db, schema, U.plan(db, real_rosters()))
    return schema, db, report


def _copy(updated):
    schema, db, _report = updated
    return schema, tdb.Database.parse(db.to_bytes(), schema)


def _rows(db, ids):
    t = db[S.SEASON]
    return sorted(tuple(sorted(t.row(i).items())) for i in range(t.count) if t.get(i, 'game_id') in ids)


def _nhl_goalies(db):
    return S._ids(db, S.ROSTER, S.TEAMS) & S._goalies(db)


@pytest.mark.game
def test_stock_dresses_only_goalies_with_rows(game_db):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    r, gid = db[S.ROSTER], S._record_ids(db)
    dressed = {gid[r.get(i, 'playerindex')] for i in range(r.count)
               if r.get(i, 'team') in S.TEAMS and (r.get(i, 'g1') or r.get(i, 'g2'))}
    assert dressed and not dressed & set(S.missing(db))


@pytest.mark.game
def test_update_gives_every_nhl_goalie_a_row(updated):
    schema, db, report = updated
    t = db[S.SEASON]
    assert report.nhl27['goalie_careers'] > 0
    assert S.check(db) == [] and not [p for p in U.check(db, schema) if S.SEASON in p]
    assert _nhl_goalies(db) <= {t.get(i, 'game_id') for i in range(t.count)}
    assert t.count <= t.max_records and S.orphans(db) == []
    keys = [(t.get(i, 'game_id'), t.get(i, 'year')) for i in range(t.count)]
    assert keys == sorted(keys)


@pytest.mark.game
def test_fill_uses_real_seasons_then_a_zero_row_and_keeps_the_others(updated):
    schema, db = _copy(updated)
    t = db[S.SEASON]
    real, blank = sorted(_nhl_goalies(db))[:2]
    gone = max(S._in_db(db)) + 1
    for i in range(t.count):
        if t.get(i, 'game_id') in (real, blank):
            t.set(i, 'game_id', gone)  # their rows become orphans, they have none
    t.sort_by('game_id', 'year')
    assert S.missing(db) == [real, blank] and S.orphans(db)
    listed = {t.get(i, 'game_id') for i in range(t.count)} & (S._ids(db, S.ROSTER) | S._ids(db, S.FREE))
    others = _rows(db, _nhl_goalies(db) - {real, blank})
    career = [[y, 0, 50, 25, 15, 5, 0, 2, 1, 3, 4, 1500, 120, 180000, 0, 1, 2, 10, 3] for y in (122, 123, 124, 125)]
    done = S.fill(db, {real: career}, shift=8)
    assert done == {real: 3, blank: 1}
    assert S.check(db) == [] and _rows(db, _nhl_goalies(db) - {real, blank}) == others
    assert listed <= {t.get(i, 'game_id') for i in range(t.count)}
    mine = [t.row(i) for i in range(t.count) if t.get(i, 'game_id') == real]
    assert [r['year'] for r in mine] == [115, 116, 117] and mine[-1]['wins'] == 25 and mine[-1]['league'] == 0
    zero = [t.row(i) for i in range(t.count) if t.get(i, 'game_id') == blank]
    year = max(t.get(i, 'year') for i in range(t.count))
    assert len(zero) == 1 and zero[0]['year'] == year and zero[0]['gamesplayed'] == 0
    assert S.fill(db) == {}
    assert S.check(tdb.Database.parse(db.to_bytes(), schema)) == []


def test_career_rows_keep_the_latest_seasons_on_the_game_clock():
    career = [[126, 0] + [1] * 17, [124, 1] + [2] * 17, [125, 0] + [3] * 17, [123, 0] + [4] * 17, [1, 2]]
    rows = S.career_rows(career, shift=8)
    assert [(r['year'], r['league'], r['wins']) for r in rows] == [(116, 1, 2), (117, 0, 3), (118, 0, 1)]
    assert S.career_rows(None) == []


@pytest.mark.game
def test_fill_raises_without_spare_rows(updated, monkeypatch):
    schema, db = _copy(updated)
    t = db[S.SEASON]
    goalie = min(_nhl_goalies(db))
    for i in range(t.count):
        if t.get(i, 'game_id') == goalie:
            t.set(i, 'game_id', goalie - 1)
    t.sort_by('game_id', 'year')
    monkeypatch.setattr(S, '_spare', lambda db, teams: iter(()))
    with pytest.raises(ValueError):
        S.fill(db)


@pytest.mark.game
def test_update_with_the_nhl27_pack_writes_real_seasons(game_db):
    import os
    from overtime_core import nhl27 as N
    pack = N.load(os.path.join(os.path.dirname(__file__), '..', 'packs', 'nhl27.json.gz'))
    if not pack or not any(p.get('career') for p in pack['players']):
        pytest.skip('no NHL 27 pack with goalie careers (packs/nhl27.json.gz is local)')
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    before = {db[S.SEASON].get(i, 'game_id') for i in range(db[S.SEASON].count)}
    U.apply(db, schema, U.plan(db, real_rosters()), nhl27=pack, start_year=2026)
    t = db[S.SEASON]
    assert S.check(db) == []
    new = (_nhl_goalies(db) - before) & set(U._goalie_careers(db, pack, 8))
    assert new
    played = [t.row(i) for i in range(t.count) if t.get(i, 'game_id') in new]
    assert {r['year'] for r in played} <= {116, 117, 118} and any(r['gamesplayed'] for r in played)


@pytest.mark.game
def test_update_of_a_roster_save_without_the_stock_career_tables(game_db):
    """Roster saves (online rosters) hold no stock career tables: the update must not need them (KeyError beta4)."""
    raw, schema = game_db
    full = tdb.Database.parse(raw, schema)
    db = tdb.Database([t for t in full.tables if t.name != S.SEASON], full._header)
    assert S.SEASON not in db
    report = U.apply(db, schema, U.plan(db, real_rosters()))
    assert 'goalie_careers' not in report.nhl27
    assert not [p for p in report.problems if S.SEASON in p]
