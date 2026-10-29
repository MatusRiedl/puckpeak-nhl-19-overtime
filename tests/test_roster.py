import pytest

from overtime_core.roster import ES_SLOTS, Roster


def _team(goalies=(90, 91)):
    """A legal synthetic team 0: 12 forwards, 6 D, 2 G, one C and two A."""
    rows, pl, bios = [], [], []
    slots = [s for s in ES_SLOTS if s not in ('g1', 'g2')]
    for i, s in enumerate(slots):
        rows.append({'team': 0, 'playerindex': i, 'jersey': i + 1, 'captain': 1 if i == 0 else 2 if i < 3 else 0,
                     s: 1})
        pl.append({'index': i, 'playerid': 100 + i, 'table': 0})
        bios.append({'game_id': 100 + i, 'position': 3 if s[-1] == 'd' else 0})
    for j, (g, s) in enumerate(zip(goalies, ('g1', 'g2'))):
        rows.append({'team': 0, 'playerindex': g, 'jersey': 30 + j, 'captain': 0, s: 1})
        pl.append({'index': g, 'playerid': 100 + g, 'table': 0})
        bios.append({'game_id': 100 + g, 'position': 4})
    return [{'index': 0, 'nickname': 'Test'}], rows, pl, bios


def rules(teams, rows, pl, bios):
    return sorted({i.rule for i in Roster(teams, rows, pl, bios).verify() if i.level == 'error'})


def test_synthetic_team_is_valid():
    assert Roster(*_team()).verify() == []


@pytest.mark.parametrize('edit, rule', [
    (lambda r, p, b: r[1].update(jersey=1), 'jersey'),
    (lambda r, p, b: r[3].update(captain=1), 'captains'),
    (lambda r, p, b: r[4].update(captain=2), 'captains'),
    (lambda r, p, b: r[0].pop('l1lw'), 'lines'),
    (lambda r, p, b: r[1].update(l1lw=1), 'lines'),
    (lambda r, p, b: r[0].update(pp1c=1) or r[1].update(pp1c=1), 'lines'),
    (lambda r, p, b: b[0].update(position=4), 'position'),
    (lambda r, p, b: b[-1].update(position=0), 'position'),
    (lambda r, p, b: r[0].update(playerindex=999), 'dangling_player'),
    (lambda r, p, b: r[1].update(playerindex=0), 'duplicate_player'),
    (lambda r, p, b: r[0].update(team=7), 'unknown_team'),
])
def test_rules(edit, rule):
    teams, rows, pl, bios = _team()
    edit(rows, pl, bios)
    assert rule in rules(teams, rows, pl, bios)


def test_capacity():
    r = Roster(*_team(), capacity={'exhibitionrostertable': (16000, 15567)})
    assert [i.rule for i in r.verify()] == ['capacity']


@pytest.mark.game
def test_default_roster_verifies(game_db):
    from overtime_core import tdb
    raw, schema = game_db
    roster = Roster.from_database(tdb.Database.parse(raw, schema))
    assert len(roster.teams) == 423 and len(roster.entries) == 8846
    errors = [str(i) for i in roster.verify() if i.level == 'error']
    assert errors == []


@pytest.mark.parametrize('edit, rule', [
    (lambda r, p, b: r[1].update(jersey=1), 'jersey'),
    (lambda r, p, b: r[3].update(captain=2), 'captains'),
    (lambda r, p, b: r[0].pop('l1lw'), 'lines'),
])
def test_pattern_rules_warn_for_a_players_own_roster(edit, rule):
    """The game plays these (docs/notes/roster-checks.md): a player's own roster saves with a warning."""
    teams, rows, pl, bios = _team()
    edit(rows, pl, bios)
    lenient = Roster(teams, rows, pl, bios).verify(strict=False)
    assert rule in {i.rule for i in lenient if i.level == 'warning'}
    assert not [i for i in lenient if i.level == 'error']
    assert rule in rules(teams, rows, pl, bios)          # strict (the roster we ship): still an error


@pytest.mark.parametrize('edit, rule', [
    (lambda r, p, b: r[0].update(playerindex=999), 'dangling_player'),
    (lambda r, p, b: r[1].update(playerindex=0), 'duplicate_player'),
    (lambda r, p, b: r[0].update(team=7), 'unknown_team'),
    (lambda r, p, b: b[0].update(position=4), 'position'),      # a goalie in a skater place: the game crashes
    (lambda r, p, b: b[-1].update(position=0), 'position'),     # a skater in goal
])
def test_corruption_stays_an_error_when_lenient(edit, rule):
    teams, rows, pl, bios = _team()
    edit(rows, pl, bios)
    lenient = Roster(teams, rows, pl, bios).verify(strict=False)
    assert rule in {i.rule for i in lenient if i.level == 'error'}
    assert Roster(*_team(), capacity={'exhibitionrostertable': (16000, 15567)}).verify(strict=False)[0].level == 'error'
