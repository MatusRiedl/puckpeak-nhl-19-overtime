"""Team strategies: layout, ranges, read / write / reset, custom teams."""
import pytest

from overtime_core import strategy as S
from overtime_core import tdb


def test_layout():
    d = S.describe()
    assert [s['title'] for s in d][:2] == ['Team', 'Forward Line 1'] and len(d) == 8
    assert sum(len(s['fields']) for s in d) == len(S.FIELDS) == 40
    pp = next(f for s in d for f in s['fields'] if f['field'] == 'pp')
    assert pp['options'] == ['Shooting', 'Overload', 'Umbrella'] and pp['top'] == 2
    assert S.top('forward3_bias2') == 10 and S.top(S.TRAP) == 6 and S.label('team_bias2') == "Team tendency 2"
    assert S.slider_words('forward1_bias3') == ("Cycle", "Shoot") and S.label('forward2_bias2') == "Line 2 tendency 2"
    assert [f['field'] for f in d[1]['fields']] == ['offense1'] + [f'forward1_bias{k}' for k in (1, 3, 4, 5, 2)]
    assert S.label('team_bias1') == "PP Carry or Dump" and S.slider_words('team_bias1') == ("PP Carry", "PP Dump")
    assert S.slider_words('forward1_bias6') is None and S.top('forward1_bias6') is None and S.VERIFIED


def test_clean():
    ok, problems = S.clean({'pp': 2, 'pk': 3, 'forward1_bias1': 10, 'threes_offense': 1, 'defense': True})
    assert ok == {'pp': 2, 'forward1_bias1': 10}
    assert len(problems) == 3 and any('Penalty Kill' in p for p in problems)


@pytest.mark.game
def test_stock_values_in_range_and_rows(game_db):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    assert S.out_of_range(db) == []
    for team in range(31):
        assert S.locate(db, team)[0].name == S.STRATEGIES
    t, _row = S.locate(db, 499)
    assert t.name == S.CUSTOM and S.locate(db, 399)[0].name == S.STRATEGIES
    every = S.read(db, 27, every=True)
    assert len(every) == 72 and every['threes_offense'] == 2
    assert S.top('team_bias4', t) == 15


@pytest.mark.game
def test_write_reset_and_round_trip(game_db):
    raw, schema = game_db
    db, stock = tdb.Database.parse(raw, schema), tdb.Database.parse(raw, schema)
    before = S.read(db, 499)
    writes = []
    setter = lambda name, row, f, v: (writes.append((name, f)), db[name].set(row, f, v))
    values, problems = S.clean({'pp': 2, 'oz_forecheck': 3, 'forward2_bias4': 9, 'defense3_bias1': 0})
    assert problems == [] and S.write(db, 499, values, setter) == len(writes) >= 3
    assert {n for n, _f in writes} == {S.CUSTOM}
    assert S.write(db, 499, values, setter) == 0 and S.read(db, 499) == {**before, **values}
    assert S.read(db, 0) == S.read(stock, 0)  # nothing else moved
    blob = db.to_bytes()
    again = tdb.Database.parse(blob, schema)
    assert again.to_bytes() == blob and S.read(again, 499) == {**before, **values}
    S.write(db, 27, {'pk': 2, 'forward1_bias1': 10})
    db[S.STRATEGIES].set(S.locate(db, 27)[1], 'forward1_bias2', 12)
    assert S.out_of_range(db) == [f"team 27: strategy Line 1 tendency 2 is 12, the game's values go to 10"]
    assert S.out_of_range(db, source=db) == []
    assert S.reset(db, stock, 27) == 3 and S.read(db, 27, every=True) == S.read(stock, 27, every=True)
    with pytest.raises(KeyError):
        S.write(db, 999, {'pp': 1})
