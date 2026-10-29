"""A team's strategies ("Build your AI"), idea and menu words from PS3 Legacy `strategy.py`.

    exhibitionteamstrategies (EeYo)   one row per team, key `index`: 0-30 the NHL teams, up to 683 (423 rows, room 519)
    customteamstrategies (IEZE)       the custom teams 400-501 (55 rows, full): Seattle is 499

73 fields: `index`; 3-bit choices (forecheck, pressure, special teams, each line's offence); 4-bit sliders between two
words for the team, each forward line and each defence pair (stock values 1-8, 5 in the middle); NHL Threes' own copy
(`threes_*`) and three breakout values the stock data never varies.

The choice words and ranges are the PS3 game's menu (Legacy lab round 28); NHL 19 uses the same words in the same
order. The slider words are NHL 19's own text (loc eng_us: TXT_FORWARD_BIAS1/3/4/5_LEFT/RIGHT, TXT_DEFENSE_BIAS1-2_*,
TXT_TEAM_PP_CARRY_AND_DUMP_*). VERIFIED (2026-10-19, docs/notes/editors.md V1): the in-game Play Now > Edit Lines and
Strategies > Edit Strategies screen read for Pittsburgh, Utah and Anaheim matches every choice and slider here. The game
shows team bias 1 as "PP Carry/Dump" and a forward line's sliders as BIAS 1, 3, 4, 5 (Carry/Dump, Cycle/Shoot,
Efficiency/Energy, Don't Block/Block). Forward bias 2 and team bias 2 are varied by the stock data but not on the game's
screen; the tab keeps them last, without the game's words. The forward line's Cycle/Shoot row is taken to be bias 3 by
its text id (bias 6 holds the same stock 5 everywhere, so the screen cannot tell them apart).
"""
STRATEGIES, CUSTOM = 'exhibitionteamstrategies', 'customteamstrategies'
KEY = 'index'
FIRST_CUSTOM = 400
VERIFIED = True

_OFFENCE = ("Overload", "Crash the Net", "Behind the Net")
CHOICES = {
    'oz_forecheck': ("Forecheck", ("1-2-2 Passive", "2-3", "Weak Side Lock", "1-2-2 Aggressive")),
    'nz_forecheck': ("Neutral Zone", ("1-3-1", "1-4", "1-2-2 Red", "1-2-2 Blue")),
    'opressure': ("Offensive Pressure", ("Defend Lead", "Conservative", "Standard", "Aggressive", "Full Attack")),
    'dpressure': ("Defensive Pressure", ("Protect Net", "Contain Puck", "Normal", "Puck Side Attack", "High Pressure")),
    'defense': ("Defensive Strategy", ("Collapsing", "Staggered", "Tight Point")),
    'pk': ("Penalty Kill", ("Passive Box", "Large Box", "Diamond")),
    'pp': ("Power Play", ("Shooting", "Overload", "Umbrella")),
    **{f"offense{n}": (f"Line {n} Offence", _OFFENCE) for n in range(1, 5)},
}
# slider words per bias number, in the game's screen order; None: a tendency the stock data never varies (not shown).
# Bias 2 of a forward line and of the team: varied by the stock data, not on the game's screen (no words known).
_FORWARD = {1: ("Carry", "Dump"), 3: ("Cycle", "Shoot"), 4: ("Efficiency", "Energy"), 5: ("Don't Block", "Block"),
            2: ("Low", "High")}
_DEFENCE = {1: ("Hold Line", "Pinch"), 2: ("Cycle", "Shoot")}
_TEAM = {1: ("PP Carry", "PP Dump"), 2: ("Low", "High")}
_NAMES = {'team_bias1': "PP Carry or Dump", 'team_bias2': "Team tendency 2",
          **{f"forward{n}_bias2": f"Line {n} tendency 2" for n in range(1, 5)}}
SLIDER_TOP = 10  # 0 .. 10, 5 in the middle
TRAP = 'trap_forecheck_bias'
TRAP_TOP = 6  # NZ ... FC, 3 in the middle

SECTIONS = ([("Team", [('oz_forecheck', 'choice'), ('nz_forecheck', 'choice'), (TRAP, 'slider')]
              + [(f, 'choice') for f in ('opressure', 'dpressure', 'defense', 'pk', 'pp')]
              + [(f'team_bias{k}', 'slider') for k in _TEAM])]
            + [(f"Forward Line {n}", [(f"offense{n}", 'choice')] + [(f"forward{n}_bias{k}", 'slider') for k in _FORWARD])
               for n in range(1, 5)]
            + [(f"Defence Pair {n}", [(f"defense{n}_bias{k}", 'slider') for k in _DEFENCE]) for n in range(1, 4)])
FIELDS = tuple(f for _, rows in SECTIONS for f, _ in rows)  # what the Strategy tab edits
assert len(FIELDS) == 40 and len(set(FIELDS)) == 40


def slider_words(field):
    """(left, right) words of a slider, or None for a tendency that is not shown."""
    if field == TRAP:
        return ("NZ", "FC")
    head, _, k = field.rpartition('_bias')
    if not head:
        return None
    words = _TEAM if head == 'team' else _DEFENCE if head.startswith('defense') else _FORWARD
    return words.get(int(k))


def label(field):
    if field in CHOICES:
        return CHOICES[field][0]
    if field in _NAMES:
        return _NAMES[field]
    words = slider_words(field)
    return f"{words[0]} or {words[1]}" if words else field


def options(field):
    """[(value, word)] a choice offers."""
    return list(enumerate(CHOICES[field][1]))


def top(field, table=None):
    """The largest value the field may hold (for a field not shown: what its bits hold, `table` gives the width)."""
    if field in CHOICES:
        return len(CHOICES[field][1]) - 1
    if field == TRAP:
        return TRAP_TOP
    if slider_words(field):
        return SLIDER_TOP
    return (1 << table.by_name[field].width) - 1 if table is not None else None


def describe():
    """The Strategy tab's layout: [{'title', 'fields': [{'field', 'kind', 'label', 'top', 'options' | 'words'}]}]."""
    out = []
    for title, rows in SECTIONS:
        fields = []
        for f, kind in rows:
            d = {'field': f, 'kind': kind, 'label': label(f), 'top': top(f)}
            if kind == 'choice':
                d['options'] = [w for _v, w in options(f)]
            else:
                d['words'] = list(slider_words(f))
            fields.append(d)
        out.append({'title': title, 'fields': fields})
    return out


def locate(db, team):
    """(table, row) of a team's strategies, or None: custom teams (400 on) in customteamstrategies when the roster has
    it, the rest in exhibitionteamstrategies."""
    names = ([CUSTOM] if team >= FIRST_CUSTOM else []) + [STRATEGIES]
    for name in names:
        if name not in db:
            continue
        t = db[name]
        for i in range(t.count):
            if t.get(i, KEY) == team:
                return t, i
    return None


def read(db, team, every=False):
    """{field: value} of the team's strategies (every=True: all 72 fields), or None when it has no row."""
    found = locate(db, team)
    if found is None:
        return None
    t, row = found
    fields = [f.name for f in t.fields if f.name != KEY] if every else FIELDS
    return {f: t.get(row, f) for f in fields}


def clean(values):
    """(the values that may be written, plain sentences for those that may not)."""
    ok, problems = {}, []
    for field, value in sorted(values.items()):
        if field not in FIELDS:
            problems.append(f"the Strategy tab has no {field}")
        elif not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= top(field):
            problems.append(f"{label(field)}: {value!r} is not one of the game's values (0 to {top(field)})")
        else:
            ok[field] = value
    return ok, problems


def write(db, team, values, setter=None):
    """Write checked values (`clean`) into the team's row; `setter(table name, row, field, value)` writes one (default:
    straight into `db`). Only changed values are written. Returns how many were."""
    found = locate(db, team)
    if found is None:
        raise KeyError(f"no strategies row for team {team}")
    t, row = found
    n = 0
    for field, value in values.items():
        if t.get(row, field) != value:
            (setter or (lambda name, r, f, v: db[name].set(r, f, v)))(t.name, row, field, value)
            n += 1
    return n


def reset(db, default_db, team, setter=None):
    """The team's every strategy back to the game's default roster's. Returns how many values changed."""
    stock = read(default_db, team, every=True)
    if stock is None:
        raise KeyError(f"the default roster has no strategies for team {team}")
    found = locate(db, team)
    if found is None:
        raise KeyError(f"no strategies row for team {team}")
    t, row = found
    n = 0
    for field, value in stock.items():
        if t.get(row, field) != value:
            (setter or (lambda name, r, f, v: db[name].set(r, f, v)))(t.name, row, field, value)
            n += 1
    return n


def out_of_range(db, source=None):
    """Sentences for shown values outside their range that `source` (the roster this one was built from) did not
    already have."""
    def values(d):
        out = {}
        for name in (STRATEGIES, CUSTOM):
            if name in d:
                t = d[name]
                out.update({(t.get(i, KEY), f): t.get(i, f) for i in range(t.count) for f in FIELDS})
        return out
    was = values(source) if source is not None else {}
    out = []
    for (team, field), value in sorted(values(db).items()):
        if value > top(field) and was.get((team, field)) != value:
            out.append(f"team {team}: strategy {label(field)} is {value}, the game's values go to {top(field)}")
    return out
