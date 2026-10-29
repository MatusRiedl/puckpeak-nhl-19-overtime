"""Roster model over the exhibition tables of a t3db database, and the verify rules every roster must pass before
it is written (app install, server publish). Facts: docs/notes/roster-format.md.

The rules hold for every team of the game's default roster (checked by tests/test_roster.py). Two kinds:
- corruption (always errors): rows over a table's capacity, a roster row pointing at no player, bio or team, a player
  on two roster rows, a skater in a goalie place or a goalie in a skater place (the game crashes loading it);
- the default roster's patterns (PATTERN_RULES: jerseys, letters, lineup slots): errors in strict mode (the default
  and Update's own output), warnings for a player's own roster (docs/notes/roster-checks.md).
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field

TEAMS, ROSTER, PLAYERS, BIOS = ('exhibitionteams', 'exhibitionrostertable', 'exhibitionplayers',
                                'exhibitionplayerbiotable')

POSITIONS = {0: 'C', 1: 'LW', 2: 'RW', 3: 'D', 4: 'G'}
GOALIE = 4
CAPTAIN, ALTERNATE = 1, 2  # exhibitionrostertable.captain

# Even-strength lineup: every team that has players fills each of these exactly once.
ES_SLOTS = tuple('l%d%s' % (i, p) for i in range(1, 5) for p in ('lw', 'c', 'rw')) + \
    tuple('l%d%s' % (i, p) for i in range(1, 4) for p in ('ld', 'rd')) + ('g1', 'g2')
GOALIE_SLOTS = ('g1', 'g2', 'three_g1', 'three_g2')
NOT_SLOTS = {'key', 'team', 'playerindex', 'jersey', 'captain', 'rosterstatus', 'playerstyle'}
# Rules the default roster always meets but the game does not need: warnings when verify is not strict.
PATTERN_RULES = frozenset({'jersey', 'lines', 'captains'})


@dataclass(frozen=True)
class Issue:
    level: str  # 'error' or 'warning'
    rule: str
    message: str
    team: int | None = None
    player: int | None = None  # exhibitionplayers index

    def __str__(self):
        return '%s %s: %s' % (self.level, self.rule, self.message)


@dataclass
class Entry:
    """One exhibitionrostertable row: a player on a team."""
    row: int
    team: int
    player: int  # exhibitionplayers index
    jersey: int
    captain: int
    slots: frozenset = field(default_factory=frozenset)


@dataclass
class Team:
    index: int
    name: str
    entries: list = field(default_factory=list)


class Roster:
    def __init__(self, teams, roster, players, bios, capacity=None):
        """teams / roster / players / bios: row dicts of the four tables; capacity: table -> (count, max)."""
        self.capacity = capacity or {}
        self.teams = {t['index']: Team(t['index'], _clean(t.get('nickname', ''))) for t in teams}
        self.players = {p['index']: p for p in players}
        self.bios = {b['game_id']: b for b in bios}
        self.entries = []
        for i, r in enumerate(roster):
            slots = frozenset(k for k, v in r.items() if k not in NOT_SLOTS and v)
            self.entries.append(Entry(i, r['team'], r['playerindex'], r['jersey'], r['captain'], slots))

    @classmethod
    def from_database(cls, db):
        tables = [db[n] for n in (TEAMS, ROSTER, PLAYERS, BIOS)]
        capacity = {t.name: (t.count, t.max_records) for t in tables}
        return cls(*(t.rows() for t in tables), capacity=capacity)

    def bio(self, player):
        p = self.players.get(player)
        return self.bios.get(p['playerid']) if p and p['table'] == 0 else None

    def position(self, player):
        b = self.bio(player)
        return b['position'] if b else None

    def by_team(self):
        out = defaultdict(list)
        for e in self.entries:
            out[e.team].append(e)
        return out

    def verify(self, strict=True):
        """The issues of this roster. strict=False: PATTERN_RULES come out as warnings (a player's own roster)."""
        issues = []

        def err(rule, msg, team=None, player=None, level='error'):
            if not strict and rule in PATTERN_RULES:
                level = 'warning'
            issues.append(Issue(level, rule, msg, team, player))

        for name, (count, cap) in self.capacity.items():
            if count > cap:
                err('capacity', '%s has %d rows, the game allows %d' % (name, count, cap))

        seen = Counter(e.player for e in self.entries)
        for player, n in seen.items():
            if n > 1:
                err('duplicate_player', 'player %d is on %d roster rows' % (player, n), player=player)

        for e in self.entries:
            p = self.players.get(e.player)
            if p is None:
                err('dangling_player', 'roster row %d points at missing player %d' % (e.row, e.player), e.team,
                    e.player)
            elif p['table'] == 0 and p['playerid'] not in self.bios:
                err('dangling_player', 'player %d has no bio (game_id %d)' % (e.player, p['playerid']), e.team,
                    e.player)
            elif p['table'] != 0:
                err('unverified_player', 'player %d comes from table %d' % (e.player, p['table']), e.team, e.player,
                    level='warning')
            if e.team not in self.teams:
                err('unknown_team', 'roster row %d is on missing team %d' % (e.row, e.team), e.team, e.player)

        for team, entries in self.by_team().items():
            name = self.teams[team].name if team in self.teams else str(team)
            for jersey, n in Counter(e.jersey for e in entries).items():
                if n > 1:
                    err('jersey', '%s: %d players wear #%d' % (name, n, jersey), team)
            slot_count = Counter(s for e in entries for s in e.slots)
            for s in ES_SLOTS:
                if slot_count[s] != 1:
                    err('lines', '%s: line slot %s is filled %d times' % (name, s, slot_count[s]), team)
            for s, n in slot_count.items():
                if s not in ES_SLOTS and n > 1:
                    err('lines', '%s: slot %s is filled %d times' % (name, s, n), team)
            for e in entries:
                pos = self.position(e.player)
                if pos is None:
                    continue
                for s in e.slots:
                    if s in GOALIE_SLOTS and pos != GOALIE:
                        err('position', '%s: %s in goalie slot %s' % (name, POSITIONS.get(pos), s), team, e.player)
                    elif s in ES_SLOTS and s not in GOALIE_SLOTS and pos == GOALIE:
                        err('position', '%s: goalie in skater slot %s' % (name, s), team, e.player)
            caps = Counter(e.captain for e in entries)
            if caps[CAPTAIN] > 1 or caps[CAPTAIN] + caps[ALTERNATE] > 3:
                err('captains', '%s: %d captains and %d alternates' % (name, caps[CAPTAIN], caps[ALTERNATE]), team)
        return issues


def _clean(s):
    return ''.join(ch for ch in s if ch.isprintable()).strip()
