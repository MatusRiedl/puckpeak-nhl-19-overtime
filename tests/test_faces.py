"""Player type and face: the type numbers of each position, writing a type (ratings record, roster entry, skill_*),
faces copied, checked against the parts the game's roster wears."""
import pytest

from overtime_core import faces as F, ratings, tdb


def test_type_numbers_follow_the_position():
    assert [s for s, _ in F.type_choices(0)] == [5, 6, 7, 8, 9, 10]
    assert [s for s, _ in F.type_choices(3)] == [1, 2, 3, 4]
    assert [s for s, _ in F.type_choices(F.GOALIE)] == [0, 1, 2]
    assert F.type_label(7) == 'SNP · Sniper' and F.type_label(2, goalie=True) == 'BUT · Butterfly'
    assert F.type_label(42) == 'Type 42' and F.type_name(0) is None


def test_wrong_face_parts_and_colours():
    valid = {'head': {1, 60000, 60001}, 'hair': {-1, 3}, 'brows': {0}, 'beard': {0}}
    assert F.wrong({'head': 60001, 'hair': -1, 'skin': 10, 'eyes': 0}, valid) is None
    assert F.wrong({'head': 5}, valid) == 'head 5 is not one the game has'
    assert F.wrong({'skin': 0}, valid) == 'skin colour 0 is not 1-10'
    assert F.wrong({'eyes': 7}, valid) == 'eye colour 7 is not 0-6'
    assert F.generic(valid) == [60000, 60001]


@pytest.fixture
def db(game_db):
    raw, schema = game_db
    return tdb.Database.parse(raw, schema)


def _named(db, last):
    B, P = db[F.BIOS], db[F.PLAYERS]
    gid = next(B.get(i, 'game_id') for i in range(B.count) if B.get(i, 'lastname') == last)
    return next(P.get(i, 'index') for i in range(P.count) if P.get(i, 'playerid') == gid and P.get(i, 'table') == 0)


@pytest.mark.game
def test_set_type_writes_ratings_record_and_roster_entry(db):
    pi = _named(db, 'McDavid')
    p = F.Player(db, pi)
    assert F.type_class(p.position) == 'F' and len(p.entries) == 1
    A, R = db[p.ai_table], db[F.ROSTER]
    old = A.get(p.ai, F.STYLE)
    new = 7 if old != 7 else 6
    with pytest.raises(ValueError):
        F.set_type(db, pi, 2)  # a defenceman's type
    model = ratings.Model.fit(A)
    changed = F.set_type(db, pi, new, model=model)
    assert A.get(p.ai, F.STYLE) == new and R.get(p.entries[0], F.STYLE) == new
    assert {(t, f) for t, _, f, _, _ in changed} >= {(F.SKATERS, F.STYLE), (F.ROSTER, F.STYLE)}
    want = model.predict(A.row(p.ai))
    assert all(A.get(p.ai, f) == v for f, v in want.items())
    assert F.set_type(db, pi, new, model=model) == []
    assert F.type_problems(db) == []
    db[F.BIOS].set(p.bio, 'position', F.DEFENCE)  # moved to defence, still a forward type
    assert [g for g, _ in F.type_problems(db)] == [p.game_id]


@pytest.mark.game
def test_goalie_type(db):
    pi = _named(db, 'Price')
    p = F.Player(db, pi)
    assert p.ai_table == F.GOALIES
    F.set_type(db, pi, 0)
    assert db[F.GOALIES].get(p.ai, F.STYLE) == 0
    with pytest.raises(ValueError):
        F.set_type(db, pi, 7)


@pytest.mark.game
def test_copy_a_face_and_check_it(db, game_db):
    raw, schema = game_db
    default = tdb.Database.parse(raw, schema)
    valid = F.parts(default)
    assert len(valid['head']) == 541 and len(F.generic(valid)) == 209 and len(valid['hair']) == 57
    assert F.problems(db, valid) == []
    B = db[F.BIOS]
    a, b = F.Player(db, _named(db, 'McDavid')).bio, F.Player(db, _named(db, 'Crosby')).bio
    face = F.read(B.row(b))
    assert F.write(db, a, face) > 0
    assert F.read(B.row(a)) == face and B.get(a, 'headtexture') == face['head']
    assert F.write(db, a, face) == 0
    assert F.problems(db, valid, before=default) == []
    F.write(db, a, {'head': 59999, 'skin': 3})
    gid = B.get(a, 'game_id')
    assert F.problems(db, valid, before=default) == [(gid, 'head 59999 is not one the game has')]
    with pytest.raises(KeyError):
        F.write(db, a, {'nose': 1})
