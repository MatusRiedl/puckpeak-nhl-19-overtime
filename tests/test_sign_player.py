"""rosterupdate.sign_player: a free agent signs with an NHL club (A3). Runs on the game's own default roster."""
import pytest

from overtime_core import nhl27 as N, rosterupdate as U
from overtime_roster.app import sources

pytestmark = pytest.mark.game


@pytest.fixture(scope='module')
def game(game_dir):
    return sources.GameData(game_dir)


@pytest.fixture
def db(game):
    return game.default_db()


def free_skater(db, name=None):
    state = U.State(db)
    for pi in sorted(state.free):
        b = state.bio(pi)
        if b and b['position'] <= 3 and b['team'] == -1 and not any(p in state.entry for p in state.pis_of[b['game_id']]):
            return b
    raise AssertionError('no free skater in the default roster')


def club_rows(db, team):
    t = db[U.ROSTER]
    return [i for i in range(t.count) if t.get(i, 'team') == team]


def test_a_free_agent_signs_with_a_club(db, game):
    b = free_skater(db)
    before = len(club_rows(db, 0))
    problems = U.check(db, game.schema())        # the stock database's own (Arizona is not Utah here)
    name, pi, rows = U.sign_player(db, b['game_id'], 0, 1_250_000, 2, two_way=False)
    assert name == f"{b['firstname']} {b['lastname']}" and rows == before + 1 == len(club_rows(db, 0))
    state = U.State(db)
    assert pi not in state.free and state.entry[pi] == (U.ROSTER, 0)
    now = state.bio(pi)
    assert (now['team'], now['proteam'], now['contractstatus']) == (0, 0, 0)
    assert now['contractdollars'] == N.units(1_250_000) and now['contractlength'] == 2
    assert now['contractismultiyear'] == 1 and now['contractis2way'] == 0 and now['extensionlength'] == 0
    t = db[U.ROSTER]
    keys = sorted(t.get(i, 'key') for i in club_rows(db, 0))
    assert keys == [U.KEYS_PER_TEAM * 0 + n for n in range(len(keys))]
    jerseys = [t.get(i, 'jersey') for i in club_rows(db, 0)]
    assert len(set(jerseys)) == len(jerseys)
    assert U.check(db, game.schema()) == problems      # the signing adds none
    again = type(db).parse(db.to_bytes(), game.schema())
    assert U.State(again).entry[pi] == (U.ROSTER, 0)


def test_the_deal_has_the_fields_of_every_club_deal(db):
    b = free_skater(db)
    _name, pi, _rows = U.sign_player(db, b['game_id'], 5, 850_000, 1, two_way=True)
    now = U.State(db).bio(pi)
    assert {f: now[f] for f in N.CONTRACT_FIELDS} == {'contractdollars': N.units(850_000), 'contractlength': 1,
                                                       'contractis2way': 1, 'contractismultiyear': 0,
                                                       'extensionlength': 0, 'extensiondollars': 0,
                                                       'extensionis2way': 0}


@pytest.mark.parametrize('team, dollars, years, what', [
    (T_SEA := 499, 1_000_000, 1, 'Seattle'),
    (31, 1_000_000, 1, 'NHL clubs'),
    (3, 1_000_000, 0, 'seasons'),
    (3, 90_000_000, 1, 'seasons'),
])
def test_refusals_change_nothing(db, team, dollars, years, what):
    b = free_skater(db)
    raw = db.to_bytes()
    with pytest.raises(U.UpdateError, match=what):
        U.sign_player(db, b['game_id'], team, dollars, years)
    assert db.to_bytes() == raw


def test_a_player_on_a_roster_cannot_sign(db):
    state = U.State(db)
    pi = next(iter(p for p, e in state.entry.items() if e[0] == U.ROSTER and e[1] == 2))
    gid = db[U.PLAYERS].row(next(i for i in range(db[U.PLAYERS].count) if db[U.PLAYERS].get(i, 'index') == pi))['playerid']
    raw = db.to_bytes()
    with pytest.raises(U.UpdateError, match='not a free agent'):
        U.sign_player(db, gid, 3, 1_000_000, 1)
    with pytest.raises(U.UpdateError, match='not in this roster'):
        U.sign_player(db, 99999999, 3, 1_000_000, 1)
    assert db.to_bytes() == raw


def test_his_own_number_unless_the_club_has_it(db):
    b = free_skater(db)
    t = db[U.ROSTER]
    taken = {t.get(i, 'jersey') for i in club_rows(db, 7)}
    _name, pi, _rows = U.sign_player(db, b['game_id'], 7, 1_000_000, 1)
    n = U.State(db).bio(pi)['jersey']
    assert 1 <= n <= 99 and sum(t.get(i, 'jersey') == n for i in club_rows(db, 7)) == 1
    if 1 <= b['jersey'] <= 99 and b['jersey'] not in taken:
        assert n == b['jersey']
