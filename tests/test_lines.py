"""Auto lines: every slot dealt once, 20 dressed, the default roster's rules, idempotent."""
from collections import Counter

import pytest

from overtime_core import lines as L
from overtime_core import roster, tdb


def player(row, pos, q, right=False, **ai):
    bio = {'position': pos, 'handedness': int(right)}
    return L._Player(row, {'playerindex': 1000 + row}, bio, {'skill_overall': q, **ai})


def squad(c=4, lw=4, rw=4, d=6, g=2, extra=3):
    out, row = [], 0
    for pos, n in ((L.C, c), (L.LW, lw), (L.RW, rw), (L.D, d), (roster.GOALIE, g), (L.C, extra)):
        for k in range(n):
            out.append(player(row, pos, 90 - k, right=(pos == L.D and k % 2 == 1)))
            row += 1
    return out


def holders(slots):
    return Counter(p.row for p in slots.values())


def test_slots_and_groups():
    assert len(L.SLOTS) == 87 and set(L.GROUPS['Lines']) == set(roster.ES_SLOTS)


def test_deal_fills_every_slot_with_the_best_players():
    ps = squad()
    s = L.deal(ps)
    assert set(s) == set(L.SLOTS)
    assert set(range(23)) - set(holders(s)) == {3, 7, 11}  # the three 87 forwards sit, the spare 88-90 centres play
    assert s['g1'].q > s['g2'].q and s['l1c'].q == 90 and s['l1lw'].pos == L.LW and s['l1rw'].pos == L.RW
    assert all(s[f'l{k}rd'].right and not s[f'l{k}ld'].right for k in (1, 2, 3))
    threes = [s[x].row for x in L.GROUPS['Threes']]
    assert len(set(threes)) == 7
    assert all(p.pos == roster.GOALIE for k, p in s.items() if k in roster.GOALIE_SLOTS)
    assert all(p.pos != roster.GOALIE for k, p in s.items() if k not in roster.GOALIE_SLOTS)


def test_deal_fills_in_short_positions():
    s = L.deal(squad(c=2, lw=5, rw=5, d=5, extra=0) + [player(99, L.RW, 50)])
    assert len(holders(s)) == 20
    assert sum(1 for k in ('l1c', 'l2c', 'l3c', 'l4c') if s[k].pos != L.C) == 2
    assert sum(1 for k in ('l1ld', 'l1rd', 'l2ld', 'l2rd', 'l3ld', 'l3rd') if s[k].pos != L.D) == 1


def test_deal_is_deterministic_and_needs_twenty():
    a, b = L.deal(squad()), L.deal(list(reversed(squad())))
    assert {k: p.row for k, p in a.items()} == {k: p.row for k, p in b.items()}
    with pytest.raises(L.NotEnoughPlayers):
        L.deal(squad(g=1))
    with pytest.raises(L.NotEnoughPlayers):
        L.deal(squad(c=2, lw=2, rw=2, d=6, extra=0))


@pytest.mark.game
def test_default_roster_follows_the_rules(game_db):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    fields = {f.name for f in db[L.ROSTER].fields} - roster.NOT_SLOTS
    assert fields == set(L.SLOTS)
    r = db[L.ROSTER]
    dressed = Counter(r.get(i, 'team') for i in range(r.count) if r.get(i, L.DRESSED))
    for team in range(31):
        assert L.check_groups(db, team) == [] and dressed[team] == 20


@pytest.mark.game
def test_build_every_team(game_db):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    writes = []
    setter = lambda table, row, f, v: (writes.append((row, f)), db[table].set(row, f, v))
    built = {team: L.build(db, team, setter) for team in range(31)}
    assert writes and all(len(b) == 87 for b in built.values())
    r = db[L.ROSTER]
    dressed = Counter(r.get(i, 'team') for i in range(r.count) if r.get(i, L.DRESSED))
    for team in range(31):
        assert L.check_groups(db, team) == [] and dressed[team] == 20
        for s in L.SLOTS:
            assert sum(1 for i in range(r.count) if r.get(i, 'team') == team and r.get(i, s)) == 1, (team, s)
    assert [i for i in roster.Roster.from_database(db).verify() if i.level == 'error'] == []
    writes.clear()
    assert {team: L.build(db, team, setter) for team in range(31)} == built and writes == []
    blob = db.to_bytes()
    assert tdb.Database.parse(blob, schema).to_bytes() == blob


def _fresh(game_db):
    raw, schema = game_db
    return tdb.Database.parse(raw, schema)


def _held(db, team, slot):
    r = db[L.ROSTER]
    return [r.get(i, 'playerindex') for i in range(r.count) if r.get(i, 'team') == team and r.get(i, slot)]


def _places(db, team, pi):
    r = db[L.ROSTER]
    i = next(i for i in range(r.count) if r.get(i, 'team') == team and r.get(i, 'playerindex') == pi)
    return {s for s in L.SLOTS if r.get(i, s) and L.GROUP_OF[s] != L.THREES}, bool(r.get(i, L.DRESSED))


def _scratch_forward(db, team):
    r = db[L.ROSTER]
    return next(p.index for p in L.players_of(db, team) if p.pos in (L.C, L.LW, L.RW) and not r.get(p.row, L.DRESSED))


@pytest.mark.game
def test_place_swaps_inside_a_group(game_db):
    db = _fresh(game_db)
    a, b = _held(db, 11, 'pp1c')[0], _held(db, 11, 'pp2c')[0]
    assert a != b
    changes = L.place(db, 11, 'pp2c', a)
    assert _held(db, 11, 'pp2c') == [a] and _held(db, 11, 'pp1c') == [b]
    assert {s for s, _, _ in changes} == {'pp1c', 'pp2c'}
    assert L.check_lineup(db, 11) == []


@pytest.mark.game
def test_scratch_needs_a_lineup_place_then_takes_over(game_db):
    db = _fresh(game_db)
    s = _scratch_forward(db, 11)
    with pytest.raises(L.NotDressed):
        L.place(db, 11, 'pp1c', s)
    had = _held(db, 11, 'l1c')[0]
    places, _ = _places(db, 11, had)
    assert 'l1c' in places and len(places) > 1
    L.place(db, 11, 'l1c', s)
    assert _places(db, 11, s) == (places, True)
    assert _places(db, 11, had) == (set(), False)
    assert L.check_lineup(db, 11) == []
    r = db[L.ROSTER]
    assert sum(1 for i in range(r.count) if r.get(i, 'team') == 11 and r.get(i, L.DRESSED)) == 20


@pytest.mark.game
def test_place_clears_and_refuses(game_db):
    db = _fresh(game_db)
    with pytest.raises(KeyError):
        L.place(db, 11, 'nope', None)
    other = _held(db, 12, 'l1c')[0]
    with pytest.raises(ValueError):
        L.place(db, 11, 'l1c', other)
    assert L.place(db, 11, 'x1', None) and _held(db, 11, 'x1') == []
    assert L.check_lineup(db, 11) == []  # extra attackers may stay empty
    L.place(db, 11, 'l1c', None)
    assert L.check_lineup(db, 11) == ['l1c is held by 0 players (the game needs exactly one)']


@pytest.mark.game
def test_deal_groups_touches_only_the_named_groups(game_db):
    db = _fresh(game_db)
    a = _held(db, 11, 'pp1c')[0]
    L.place(db, 11, 'pp2c', a)
    L.place(db, 11, 's1', _held(db, 11, 's5')[0])
    r = db[L.ROSTER]
    rows = [i for i in range(r.count) if r.get(i, 'team') == 11]
    pp = set(L.GROUPS['Power play']) | set(L.GROUPS['Power play 4 on 3'])
    before = {(i, s): r.get(i, s) for i in rows for s in L.SLOTS + (L.DRESSED,) if s not in pp}
    dealt = L.deal_groups(db, 11, ['Power play', 'Power play 4 on 3'])
    assert set(dealt) == pp and {(i, s): r.get(i, s) for (i, s) in before} == before
    assert all(_held(db, 11, x) == [pi] for x, pi in dealt.items())
    assert L.check_lineup(db, 11) == []
    writes = []
    L.deal_groups(db, 11, ['Power play', 'Power play 4 on 3'], setter=lambda *w: writes.append(w))
    assert writes == []
    with pytest.raises(KeyError):
        L.deal_groups(db, 11, ['Nope'])
