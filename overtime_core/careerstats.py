"""Career goalie rows for the NHL teams' goalies.

In the stock roster every dressed NHL goalie has a row in `stockcareerseasongoaliestats`; goalies the roster update
brings in (new records, or stock players who had none) do not. This restores that rule with real seasons (it was
suspected of, but is not, the Play Now crash: that was the roster keys, rosterupdate.KEYS_PER_TEAM). The table is full (2054 records) and sorted by
(game_id, year), so `fill` gives each NHL (and Play Now Seattle) goalie without a row his latest real seasons (NHL 27's
career rows, `careers`, at most `SEASONS`), or one zeroed row of the latest season when there are none, and sorts the
table again. The rows come from goalies the roster no longer has (orphans) first, then from goalies on no roster and
no free-agent list, then from the oldest seasons of goalies who keep at least one row (those off the NHL teams
first). Orphan rows nobody needs are removed.
"""
from . import teams as T

SEASON = 'stockcareerseasongoaliestats'
ROSTER, PLAYERS, BIOS, FREE = ('exhibitionrostertable', 'exhibitionplayers', 'exhibitionplayerbiotable',
                               'exhibitionfreeagents')
GOALIE = 4
SEASONS = 3
TEAMS = tuple(range(31)) + (T.SEATTLE_PLAY_NOW,)
STATS = ('gamesplayed', 'wins', 'losses', 'otlosses', 'ties', 'sowins', 'solosses', 'otwins', 'shutouts',
         'shotsagainst', 'goalsagainst', 'timeinnetseconds', 'goals', 'assists', 'penaltyminutes',
         'shootoutshotsagainst', 'shootoutgoalsagainst')
FIELDS = ('year', 'league') + STATS  # a career row in the NHL 27 pack: these values, in this order


def _record_ids(db):
    p = db[PLAYERS]
    return {p.get(i, 'index'): p.get(i, 'playerid') for i in range(p.count) if p.get(i, 'table') == 0}


def _ids(db, table, teams=None):
    """game_ids of the players on `table` (a roster, or the free agents), of `teams` only when given."""
    if table not in db:
        return set()
    gid, t = _record_ids(db), db[table]
    return {gid[t.get(i, 'playerindex')] for i in range(t.count)
            if t.get(i, 'playerindex') in gid and (teams is None or t.get(i, 'team') in teams)}


def _goalies(db):
    b = db[BIOS]
    return {b.get(i, 'game_id') for i in range(b.count) if b.get(i, 'position') == GOALIE}


def _in_db(db):
    b = db[BIOS]
    return {b.get(i, 'game_id') for i in range(b.count)}


def missing(db, teams=TEAMS):
    """Sorted game_ids of the goalies of `teams` without a career season row."""
    t = db[SEASON]
    have = {t.get(i, 'game_id') for i in range(t.count)}
    return sorted((_ids(db, ROSTER, teams) & _goalies(db)) - have)


def orphans(db):
    """Row numbers of the rows whose game_id is no player of the roster."""
    t, known = db[SEASON], _in_db(db)
    return [i for i in range(t.count) if t.get(i, 'game_id') not in known]


def _spare(db, teams):
    """Row numbers that can be given away, best first; a goalie on a roster or the free agents keeps one row."""
    t = db[SEASON]
    known = _in_db(db)
    listed = _ids(db, ROSTER) | _ids(db, FREE)
    main = _ids(db, ROSTER, teams)
    left = {}
    for i in range(t.count):
        left[t.get(i, 'game_id')] = left.get(t.get(i, 'game_id'), 0) + 1
    order = sorted(range(t.count), key=lambda i: (t.get(i, 'game_id') in known, t.get(i, 'game_id') in listed,
                                                  t.get(i, 'game_id') in main, t.get(i, 'year'), t.get(i, 'game_id')))
    for i in order:
        g = t.get(i, 'game_id')
        if g not in listed or left[g] > 1:
            left[g] -= 1
            yield i


def career_rows(career, shift=0, seasons=SEASONS):
    """The latest `seasons` rows of a pack career ([[FIELDS values]]), as dicts, years moved back `shift` (the
    game's 2018 clock, teams.year_shift)."""
    rows = sorted((dict(zip(FIELDS, v)) for v in career or [] if len(v) == len(FIELDS)),
                  key=lambda r: (r['year'], r['league']))[-seasons:]
    for r in rows:
        r['year'] -= shift
    return rows


def fill(db, careers=None, shift=0, teams=TEAMS, seasons=SEASONS):
    """Give every goalie of `missing` his latest real seasons (`careers`: {game_id: pack career}) or one zeroed row
    of the latest season, then drop the orphan rows left. Returns {game_id: rows written}; raises ValueError when
    there are not enough spare rows for one row each."""
    need = missing(db, teams)
    t = db[SEASON]
    year = max(t.get(i, 'year') for i in range(t.count))
    want = {g: career_rows((careers or {}).get(g), shift, seasons) or [dict(year=year, league=0)] for g in need}
    spare = list(_spare(db, teams))
    listed = _ids(db, ROSTER) | _ids(db, FREE)
    cheap = sum(1 for i in spare if t.get(i, 'game_id') not in listed)  # orphans and goalies on no list
    if len(spare) < len(need):
        raise ValueError(f"{SEASON}: {len(need)} goalies need a row, {len(spare)} spare")
    # one row each (the latest season), then the earlier ones while rows nobody listed are left
    plan = [(g, rows[-1]) for g, rows in want.items()]
    extra = [(g, r) for g, rows in want.items() for r in reversed(rows[:-1])]
    plan += extra[:max(0, cheap - len(plan))]
    for i, (g, r) in zip(spare, plan):
        t.set(i, 'game_id', g)
        for c in ('year', 'league') + STATS:
            t.set(i, c, r.get(c, 0))
    for i in reversed(orphans(db)):
        t.delete(i)
    t.sort_by('game_id', 'year')
    done = {}
    for g, _r in plan:
        done[g] = done.get(g, 0) + 1
    return done


def check(db, teams=TEAMS):
    """Problems: goalies of `teams` without a row, orphan rows, an unsorted table."""
    t = db[SEASON]
    keys = [(t.get(i, 'game_id'), t.get(i, 'year')) for i in range(t.count)]
    problems = [f"goalie {g} has no {SEASON} row" for g in missing(db, teams)]
    if orphans(db):
        problems.append(f"{SEASON}: {len(orphans(db))} rows of players not in the roster")
    if keys != sorted(keys):
        problems.append(f"{SEASON} is not sorted by game_id, year")
    return problems
