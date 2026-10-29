"""The real calendar in the schedule tables: NHL.com schedule flattening, team mapping, trim, apply and check.
`tests/data/nhl_schedule_20262027.json` is the 2026-27 regular season as NHL.com listed it on 2026-10-16
([date, home, away], 1,344 games)."""
import datetime
import json
import os

import pytest

from overtime_core import calendar as C
from overtime_core import nhlcom, tdb

DATA = os.path.join(os.path.dirname(__file__), 'data', 'nhl_schedule_20262027.json')


@pytest.fixture(scope='module')
def season():
    with open(DATA, encoding='utf-8') as f:
        return [tuple(g) for g in json.load(f)]


def game(gid, date, home, away, kind=2):
    return {'id': gid, 'gameType': kind, 'gameDate': date, 'homeTeam': {'abbrev': home}, 'awayTeam': {'abbrev': away}}


def test_schedule_games_keeps_one_game_type():
    body = {'games': [game(1, '2026-09-20', 'SEA', 'VAN', 1), game(2, '2026-10-01', 'CGY', 'SEA')]}
    assert nhlcom.schedule_games(body) == [{'id': 2, 'date': '2026-10-01', 'home': 'CGY', 'away': 'SEA', 'type': 2}]
    assert len(nhlcom.schedule_games(body, None)) == 2
    assert nhlcom.schedule_games({}) == []


def test_season_games_lists_each_game_once_in_date_order():
    bodies = {'SEA': {'games': [game(5, '2026-10-03', 'SEA', 'VAN'), game(2, '2026-10-01', 'CGY', 'SEA')]},
              'VAN': {'games': [game(5, '2026-10-03', 'SEA', 'VAN'), game(1, '2026-10-01', 'VAN', 'EDM'),
                                game(9, '2026-09-25', 'VAN', 'SEA', 1)]}}

    class Client:
        seen = []

        def club_schedule(self, code, season):
            self.seen.append((code, season))
            return bodies.get(code, {'games': []})
    c = Client()
    out = C.season_games(c, 2026, codes=['SEA', 'VAN'])
    assert out == [('2026-10-01', 'VAN', 'EDM'), ('2026-10-01', 'CGY', 'SEA'), ('2026-10-03', 'SEA', 'VAN')]
    assert c.seen == [('SEA', '20262027'), ('VAN', '20262027')]


def test_every_team_of_the_season_has_an_index(season):
    assert {t for _d, h, a in season for t in (h, a)} == set(C.SLOTS)
    assert sorted(C.SLOTS.values()) == list(range(32))
    with pytest.raises(C.CalendarError, match='ARI'):
        C.slot_games([('2026-10-01', 'ARI', 'SEA')])


def counts(rows):
    home, away = {}, {}
    for _d, h, a in rows:
        home[h] = home.get(h, 0) + 1
        away[a] = away.get(a, 0) + 1
    return home, away


def test_32_team_calendar_is_the_whole_season(season):
    rows = C.rows_for(season, 32)
    assert len(rows) == 1344 and rows[0][0] == '2026-09-29' and rows[-1][0] == '2027-04-10'
    home, away = counts(rows)
    assert set(home.values()) == {42} and set(away.values()) == {42} and len(home) == 32
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)


def places(season):
    """The real games in nhl32schedule's places."""
    return [(d, C.PLACE32.get(h, h), C.PLACE32.get(a, a)) for d, h, a in C.slot_games(season)]


def test_32_team_places_put_seattle_in_utahs_place(season):
    # the expansion Franchise lists Seattle in place 22 (Pacific) and Utah in 31 (run v0100-s3b)
    assert (C.SLOTS32['SEA'], C.SLOTS32['UTA'], C.CODES32[22], C.CODES32[31]) == (22, 31, 'SEA', 'UTA')
    assert sorted(C.SLOTS32.values()) == list(range(32)) and C.SLOTS['SEA'] == C.EXPANSION == 31
    rows, real = C.rows_for(season, 32), C.slot_games(season)
    assert sorted(rows) == sorted(places(season))
    sea = sorted((d, h == C.EXPANSION) for d, h, a in real if C.EXPANSION in (h, a))
    assert sea and sorted((d, h == 22) for d, h, a in rows if 22 in (h, a)) == sea
    # the 31-team tables keep Utah in 22 and fold Seattle's games out
    assert C.rows_for(season, 31) == sorted(C.trim(C.fold(real), C.GAMES), key=lambda g: g[0])


def test_fold_gives_seattles_games_to_its_opponents(season):
    played = C.slot_games(season)
    rows = C.fold(played)
    assert len(rows) == 1344 - 42 and all(C.EXPANSION not in (h, a) for _d, h, a in rows)
    home, away = counts(rows)
    assert set(home.values()) == {42} and set(away.values()) == {42} and len(home) == 31
    new = [g for g in rows if g not in set(played)]
    assert len(new) == 42 and all(h != a for _d, h, a in new)
    for d in {g[0] for g in rows}:  # nobody plays twice in a day
        teams = [t for g in rows if g[0] == d for t in g[1:]]
        assert len(teams) == len(set(teams))
    days = {}
    for d, h, a in rows:
        for t in (h, a):
            days.setdefault(t, set()).add(datetime.date.fromisoformat(d))
    one = datetime.timedelta(1)  # nobody plays three days in a row (the real season never does)
    assert not [(t, d) for t, ds in days.items() for d in ds if d + one in ds and d + 2 * one in ds]
    assert C.fold(played) == rows
    with pytest.raises(C.CalendarError, match='paired'):
        C.fold(played + [('2027-04-11', C.EXPANSION, 0)])


def test_31_team_calendar_folds_seattle_and_cuts_to_82(season):
    rows = C.rows_for(season, 31)
    assert all(C.EXPANSION not in (h, a) for _d, h, a in rows)
    home, away = counts(rows)
    assert C.GAMES == 82 and rows == C.rows_for(season, 31, 82)
    assert len(rows) == 1271 and set(home.values()) == {41} and set(away.values()) == {41} and len(home) == 31
    assert rows[0][0] == '2026-09-29' and rows[-1][0] == '2027-04-10'


def test_trim_to_82_and_rules(season):
    rows = C.rows_for(season, 32, 82)
    home, away = counts(rows)
    assert len(rows) == 1312 and set(home.values()) == {41} and set(away.values()) == {41}
    first_day = [g for g in places(season) if g[0] == '2026-09-29']
    assert first_day == [g for g in rows if g[0] == '2026-09-29']  # cuts come from mid-season
    cut = [g for g in places(season) if g not in set(rows)]
    assert len(cut) == 32 and all('2026-12-01' <= g[0] <= '2027-03-01' for g in cut)
    assert C.rows_for(season, 32, 82) == rows  # deterministic
    with pytest.raises(C.CalendarError, match='even'):
        C.rows_for(season, 32, 81)
    with pytest.raises(C.CalendarError, match='fewer'):
        C.rows_for(season, 32, 86)
    with pytest.raises(C.CalendarError, match='30-team'):
        C.rows_for(season, 30)


def test_season_date():
    assert C.season_date(9, 2, 2018) == datetime.date(2018, 10, 3)
    assert C.season_date(3, 9, 2026).year == 2027


@pytest.mark.game
def test_apply_and_check_on_the_game_database(game_db, season):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    other = db[schema.by_name('ahl32schedule').short].body_bytes()
    stock_first = C.read(db[schema.by_name('nhlschedule').short])[0]
    assert stock_first == (9, 2, 27, 15)  # TOR-MTL, 3 Oct 2018: day and month are 0-based
    expected = C.apply(db, schema, season)
    assert expected[C.TABLE32]['games'] == 1344 and expected[C.TABLE32]['per_team'] == (84, 84)
    assert expected['nhlschedule']['games'] == 1271 and expected['nhlschedule']['per_team'] == (82, 82)
    assert C.check(db, schema, expected, 2026) == []
    t32 = db[schema.by_name(C.TABLE32).short]
    assert C.read(t32)[0] == (8, 28, C.SLOTS['CAR'], C.SLOTS['FLA'])  # 29 Sep 2026
    assert db[schema.by_name('ahl32schedule').short].body_bytes() == other
    blob = db.to_bytes()
    again = tdb.Database.parse(blob, schema)
    assert again.to_bytes() == blob and C.check(again, schema, expected, 2026) == []
    # the checks catch a team playing twice in a day and tables out of step
    t32.set(1, 'home', t32.get(0, 'home'))
    fav = db[schema.by_name('favoriteteamschedule').short]
    fav.set(5, 'away', (fav.get(5, 'away') + 1) % 31)
    problems = C.check(db, schema, expected, 2026)
    assert any('twice' in p for p in problems) and any('not equal' in p for p in problems)


@pytest.mark.game
def test_apply_writes_nothing_when_a_table_is_too_small(game_db, season):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    before = db.to_bytes()
    extra = list(season)  # the season twice: 86 games each are 1,376 rows, more than 1,372
    with pytest.raises(C.CalendarError, match='do not fit'):
        C.apply(db, schema, season + extra, per32=86, per31=60)
    assert db.to_bytes() == before
