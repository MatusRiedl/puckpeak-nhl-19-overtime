"""Ratings: the data pack loader, the skill_* model, matching and writing EA-style attributes (made-up values)."""
import gzip
import json
import time

import pytest

from overtime_core import ratings as R
from overtime_core import tdb


def test_load_pack_downloads_caches_and_falls_back(tmp_path):
    pack = {'format': 1, 'generated': 'x', 'ea_ratings': []}
    raw = gzip.compress(json.dumps(pack).encode())
    assert R.load_pack(str(tmp_path), fetch=lambda url: raw) == pack
    assert R.load_pack(str(tmp_path), fetch=lambda url: (_ for _ in ()).throw(OSError('offline'))) == pack
    newer = gzip.compress(json.dumps({'format': 9}).encode())
    assert R.load_pack(str(tmp_path), fetch=lambda url: newer) == pack  # too new: the cached one
    with pytest.raises(R.PackError):
        R.load_pack(str(tmp_path / 'empty'), offline=True)


def test_the_pack_comes_from_legacys_file_server():
    # Legacy left the GitHub release asset out at 0.32.0 (format 2): that URL answers 404
    assert R.DEFAULT_PACK_URL == 'https://puckpeak.com/legacy-roster/datapack.json.gz'


def test_format_2_packs_load_and_name_the_ratings_ratings_list(tmp_path):
    row = {'name': 'A B', 'team': 'TOR', 'position': 'C', 'birth': [2000, 1, 1], 'ovr': 80, 'attrs': {}}
    two = {'format': 2, 'generated': 'y', 'ratings_list': [row], 'lines': {}}
    assert R.load_pack(str(tmp_path), fetch=lambda url: gzip.compress(json.dumps(two).encode())) == two
    assert R.usable({'format': 1}) and R.usable({'format': 2}) and not R.usable({'format': 3})
    assert R.ea_rows(two) == [row]
    assert R.ea_rows({'format': 1, 'ea_ratings': [row]}) == [row]
    assert R.ea_rows({'format': 2}) == [] and R.ea_rows(None) == []


def test_solve():
    x = R._solve([[2.0, 1.0], [1.0, 3.0]], [5.0, 10.0])
    assert abs(x[0] - 1) < 1e-4 and abs(x[1] - 3) < 1e-4


@pytest.mark.game
def test_model_matches_the_games_own_values(game_db):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    for name in (R.SKATERS, R.GOALIES):
        t0 = time.time()
        model = R.Model.fit(db[name])
        assert time.time() - t0 < 20
        rows = db[name].rows()
        exact = near = total = 0
        for r in rows:
            for f, v in model.predict(r).items():
                exact += v == r[f]
                near += abs(v - r[f]) <= 1
                total += 1
        assert exact / total > 0.9 and near / total > 0.99, (name, exact / total, near / total)


def bio_of(db, first, last):
    bios = db[R.BIOS]
    return next(i for i in range(bios.count) if (bios.get(i, 'firstname'), bios.get(i, 'lastname')) == (first, last))


@pytest.mark.game
def test_match_plan_apply(game_db):
    raw, schema = game_db
    db = tdb.Database.parse(raw, schema)
    bios = db[R.BIOS]
    picks = {}
    for pos in (3, R.GOALIE):  # one defenceman, one goalie of the default roster, by their bio
        i = next(i for i in range(bios.count) if bios.get(i, 'position') == pos and bios.get(i, 'year') > 90)
        picks[pos] = bios.row(i)
    d, g = picks[3], picks[R.GOALIE]
    born = lambda b: [b['year'] + 1900, b['month'] + 1, b['day'] + 1]
    ratings = [
        {'name': f"{d['firstname']} {d['lastname']}", 'position': 'D', 'birth': born(d),
         'attrs': {'Passing': 97, 'Defensive Awareness': 99, 'Speed': 120}},
        {'name': f"{g['firstname']} {g['lastname']}", 'position': 'G', 'birth': born(g), 'attrs': {'Glove Side High': 98}},
        {'name': f"{g['firstname']} {g['lastname']}", 'position': 'C', 'birth': born(g), 'attrs': {'Passing': 99}},
        {'name': 'Nobody Atall', 'position': 'C', 'birth': [2007, 1, 1], 'attrs': {'Passing': 99}},
    ]
    found = R.match(db, ratings)
    assert sorted((r['position'], level) for r, _row, level in found) == [('D', 'exact'), ('G', 'exact')]
    todo = R.plan(db, found)
    fields = {(name, f) for name, _row, f, _o, _n in todo}
    assert {(R.SKATERS, 'c_passing'), (R.SKATERS, 'c_defawareness'), (R.SKATERS, 'c_speed'), (R.GOALIES, 'c_gsh')} <= fields
    assert (R.SKATERS, 'skill_overall') in fields
    assert all(n <= R.TOP for *_x, n in todo)
    assert R.apply(db, todo) == len(todo) and R.plan(db, found) == []
    blob = db.to_bytes()
    assert tdb.Database.parse(blob, schema).to_bytes() == blob
