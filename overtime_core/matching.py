"""Match real players (NHL.com) to NHL 19 database players by name and birth date.

Confidence levels, best first:
  'exact'  same normalised first + last name and the same birth date
  'date'   same birth date and last name (first name differs: Alex / Alexander, Mitch / Mitchell)
  'name'   same normalised name, the only such player, birth date unknown or different by a typo (warning)
Anything else is unmatched (a new player for a free record).

`shifts`: birth years a game player may be stored behind the real one. NHL 19 counts ages from its own league year
(2018), so an updated roster keeps birth years on that clock (real - 8 for 2026-27, teams.year_shift); matching with
shifts (0, 8) finds a player before and after that update.
"""
import re
import unicodedata
from dataclasses import dataclass

_SUFFIX = re.compile(r'\b(jr|sr|ii|iii|iv)\b')


def norm(name):
    """Lower case, no accents, letters only: 'Pierre-Luc Dubois' -> 'pierreluc dubois'."""
    s = unicodedata.normalize('NFKD', name or '')
    s = ''.join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = s.replace('ø', 'o').replace('æ', 'ae').replace('ß', 'ss').replace('ł', 'l')
    s = re.sub(r"[.'`\-]", '', s)
    s = _SUFFIX.sub('', s)
    return ' '.join(re.sub(r'[^a-z ]', ' ', s).split())


@dataclass(frozen=True)
class Person:
    key: object  # caller's id (game_id, NHL.com id)
    first: str
    last: str
    birth: str = ''  # 'YYYY-MM-DD' or ''


@dataclass(frozen=True)
class Match:
    real: Person
    game: Person | None
    level: str  # 'exact', 'date', 'name' or 'none'


def shifted(birth, years):
    """'YYYY-MM-DD' `years` earlier ('' stays ''); Feb 29 stays a leap day for shifts that are multiples of 4."""
    if not birth or not years:
        return birth
    return f'{int(birth[:4]) - years:04d}{birth[4:]}'


class Matcher:
    def __init__(self, game_players, shifts=(0,)):
        self.shifts = tuple(shifts)
        self.by_full_date, self.by_last_date, self.by_full = {}, {}, {}
        for p in game_players:
            full = (norm(p.first), norm(p.last))
            self.by_full_date.setdefault((full, p.birth), []).append(p)
            self.by_last_date.setdefault((full[1], p.birth), []).append(p)
            self.by_full.setdefault(full, []).append(p)

    def match(self, real):
        full = (norm(real.first), norm(real.last))
        births = [shifted(real.birth, n) for n in self.shifts] if real.birth else []
        for index, key, level in ((self.by_full_date, full, 'exact'), (self.by_last_date, full[1], 'date')):
            hit = [p for b in births for p in index.get((key, b), [])]
            if len(hit) == 1:
                return Match(real, hit[0], level)
        hit = self.by_full.get(full)
        if hit and len(hit) == 1:
            return Match(real, hit[0], 'name')
        return Match(real, None, 'none')

    def match_all(self, reals):
        """Matches for `reals`; a game player is given to at most one real player (the best level wins)."""
        rank = {'exact': 0, 'date': 1, 'name': 2}
        found = [self.match(r) for r in reals]
        best = {}
        for i, m in enumerate(found):
            if m.game is None:
                continue
            j = best.get(m.game.key)
            if j is None or rank[m.level] < rank[found[j].level]:
                best[m.game.key] = i
        taken = set(best.values())
        return [m if m.game is None or i in taken else Match(m.real, None, 'none') for i, m in enumerate(found)]
