"""Real lines and captains: the lines and letters each NHL team played in its last games, from the data pack's
`lines` part (NHL Legacy's `tools/build_datapack.py --refresh lines`: Daily Faceoff's announced lines, else NHL.com's
last 5 game reports; Legacy `builder.lines_from_games`). docs/notes/real-lines.md.

The pack names 52 slots with lines.py's own names: even strength, the goalies, both power plays and both penalty kills.
They are laid over the team's lines group by group, each group only when every one of its slots is a different
player of the team now (and a goalie only in a goalie slot). The 20 who hold the even-strength and goalie slots
dress; a power-play or penalty-kill unit of the pack is kept only when all its players dress, else it is dealt.
Overtime, the shootout, the extra attackers and Threes are dealt from the dressed 20 (lines.deal_groups). A team
whose result lines.check_lineup finds fault with keeps the lines it had.

Letters: skaters only, one C at most, three letters in all (the pack's, then As for the best dressed skaters).
"""
from dataclasses import dataclass, field

from . import lines
from .roster import ALTERNATE, CAPTAIN, ES_SLOTS, GOALIE, NOT_SLOTS

GOALIE_PAIR = ('g1', 'g2')
REAL_GROUPS = {
    'Lines': tuple(s for s in ES_SLOTS if s not in GOALIE_PAIR),
    'Goalies': GOALIE_PAIR,
    'Power play': lines.GROUPS['Power play'],
    'Power play 4 on 3': lines.GROUPS['Power play 4 on 3'],
    'Penalty kill': lines.GROUPS['Penalty kill'],
    'Penalty kill 3 on 5': lines.GROUPS['Penalty kill 3 on 5'],
}
SPECIAL = ('Power play', 'Power play 4 on 3', 'Penalty kill', 'Penalty kill 3 on 5')
LETTERS = 3
CAPTAIN_FIELD = 'captain'


@dataclass
class Result:
    lined: list = field(default_factory=list)      # club codes that play (some of) their real lines
    refused: dict = field(default_factory=dict)    # club code -> [reason]: the team kept its lines
    lettered: list = field(default_factory=list)   # club codes whose letters were set
    date: str = ''                                 # the newest date of the lines laid

    def as_dict(self):
        return {'lined': self.lined, 'refused': self.refused, 'lettered': self.lettered, 'date': self.date}


def part(pack, season):
    """The pack's `lines` part ({club code: entry}) when it is for `season` (the year the season starts), else None."""
    real = (pack or {}).get('lines')
    if not isinstance(real, dict) or not real or (pack or {}).get('season') != season:
        return None
    return real


def apply(db, real, pis, target_of, setter=None, log=lambda msg: None):
    """Lay `real` (part()) on every club it names. `pis` {NHL.com id: exhibitionplayers index} (the update's placed
    players), `target_of(code)` -> (roster table, team) (rosterupdate.target_of; raises ValueError for a club the game
    does not have). Returns a Result."""
    out = Result()
    for code in sorted(real):
        entry = real[code] or {}
        try:
            table, team = target_of(code)
        except ValueError as err:
            out.refused[code] = [str(err)]
            continue
        if table not in db:
            continue
        if entry.get('slots'):
            problems = line_up(db, table, team, entry['slots'], pis, setter)
            if problems:
                out.refused[code] = problems
                log(f'real lines {code}: kept the lines it had ({problems[0]})')
            else:
                out.lined.append(code)
                out.date = max(out.date, str(entry.get('date') or ''))
        if entry.get('letters') and letter(db, table, team, entry['letters'], pis, setter):
            out.lettered.append(code)
    return out


def _team_rows(db, table, team):
    roster = db[table]
    return [i for i in range(roster.count) if roster.get(i, 'team') == team]


def line_up(db, table, team, wanted, pis, setter=None):
    """Write `wanted` ({slot: NHL.com id}) on one team's lines. Returns [] when written, else what was wrong (the team
    keeps what it had)."""
    roster = db[table]
    set_ = setter or (lambda table, row, f, v: db[table].set(row, f, v))
    rows = _team_rows(db, table, team)
    fields = [f.name for f in roster.fields if f.name not in NOT_SLOTS] + [lines.DRESSED]
    before = {i: {f: roster.get(i, f) for f in fields} for i in rows}
    if lines.check_lineup(db, team, table):
        try:
            lines.build(db, team, setter, table)
        except lines.NotEnoughPlayers as err:
            return [str(err)]
    players = lines.players_of(db, team, table)
    by_pi = {p.index: p for p in players}
    holder = {s: next((p for p in players if roster.get(p.row, s)), None) for s in lines.SLOTS}
    new, applied = {}, []
    for name, slots in REAL_GROUPS.items():
        got = {s: by_pi.get(pis.get(wanted.get(s))) for s in slots}
        if any(p is None for p in got.values()) or len({id(p) for p in got.values()}) != len(got):
            continue
        if any((p.pos == GOALIE) != (s in GOALIE_PAIR) for s, p in got.items()):
            continue
        new.update(got)
        applied.append(name)
    if not applied:
        return ['no group of the real lines has all its players on the team']
    for s in list(new):                                  # a defence pair: the right shot on the right
        if s.endswith('ld') and s[:-2] + 'rd' in new:
            ld, rd = new[s], new[s[:-2] + 'rd']
            if ld.right and not rd.right:
                new[s], new[s[:-2] + 'rd'] = rd, ld
    lineup = {s: new.get(s, holder[s]) for s in ES_SLOTS}
    dressed = {id(p) for p in lineup.values()}
    for p in players:                                    # even strength, goalies and who dresses
        for s in ES_SLOTS:
            v = int(lineup[s] is p)
            if roster.get(p.row, s) != v:
                set_(table, p.row, s, v)
        v = int(id(p) in dressed)
        if roster.get(p.row, lines.DRESSED) != v:
            set_(table, p.row, lines.DRESSED, v)
    special = [g for g in SPECIAL if g in applied and all(id(new[s]) in dressed for s in REAL_GROUPS[g])]
    lines.deal_groups(db, team, [g for g in lines.GROUPS if g != 'Lines' and g not in special], setter, table)
    for g in special:
        for p in players:
            for s in REAL_GROUPS[g]:
                v = int(new[s] is p)
                if roster.get(p.row, s) != v:
                    set_(table, p.row, s, v)
    problems = lines.check_lineup(db, team, table)
    if problems:
        for i, values in before.items():
            for f, v in values.items():
                if roster.get(i, f) != v:
                    set_(table, i, f, v)
    return problems


def letter(db, table, team, letters, pis, setter=None):
    """The team's C and As from `letters` ({"NHL.com id": 'C' | 'A'}): skaters only, one C at most, topped up to three
    letters with As for the best dressed skaters. A team none of whose lettered players it has keeps its letters.
    Returns whether the letters were set."""
    roster = db[table]
    set_ = setter or (lambda table, row, f, v: db[table].set(row, f, v))
    players = [p for p in lines.players_of(db, team, table) if p.pos != GOALIE]
    by_pi = {p.index: p for p in players}
    want = {}
    for nhl_id, mark in sorted(letters.items(), key=lambda kv: (kv[1] != 'C', str(kv[0]))):
        try:
            p = by_pi.get(pis.get(int(nhl_id)))
        except (TypeError, ValueError):
            p = None
        if p is None or p.row in want or len(want) >= LETTERS:
            continue
        want[p.row] = CAPTAIN if mark == 'C' and CAPTAIN not in want.values() else ALTERNATE
    if not want:
        return False
    for p in sorted(players, key=lambda p: (-bool(roster.get(p.row, lines.DRESSED)), -p.q, p.index)):
        if len(want) >= LETTERS:
            break
        want.setdefault(p.row, ALTERNATE)
    for i in _team_rows(db, table, team):
        v = want.get(i, 0)
        if roster.get(i, CAPTAIN_FIELD) != v:
            set_(table, i, CAPTAIN_FIELD, v)
    return True
