"""Elo rating and rank tiers over the confirmed matches (pure; no clock, no storage).

The rating is never stored: `rate()` folds the confirmed matches in order, so a voided match, a late confirmation or a new
season just re-folds. Only matches `overtime_core.history.resolve` calls confirmed count. Hockey is noisy and the pool is
small, so the numbers move slowly and a player is "placing" until PLACEMENT games. The same two players meeting again and
again within PAIR_WINDOW are damped (win-trading with a spoofable id gains little).
"""
import math

from . import history as H

START = 1000.0                                  # a new player is a Rookie
SCALE = 400.0
K_NEW, K_SETTLED, K_GAMES = 40.0, 24.0, 10      # a player's first K_GAMES rated games move more
MARGIN_STEP, MARGIN_MAX = 0.1, 1.5              # 1.0 for a one-goal win, +0.1 per extra goal, capped
PAIR_WINDOW = 24 * 3600                         # the same two within this many seconds are damped:
PAIR_WEIGHTS = (1.0, 1.0, 0.5, 0.25, 0.0)       # 1st, 2nd, 3rd, 4th, 5th and later game
PLACEMENT = 5                                   # rated games before a rank shows

# (name, lowest rating, line for the legend): a ladder in steps of 100 up to 1700
TIERS = (('Minor League', 0, 'Grinding in the AHL.'),
         ('Rookie', 1000, 'Cracking the main NHL roster.'),
         ('Pro', 1100, 'An established, everyday NHL regular.'),
         ('Top 6', 1200, "A core contributor driving the team's success."),
         ('Alternate Captain', 1300, 'A trusted veteran and secondary locker-room leader.'),
         ('Captain', 1400, 'The ultimate team leader and franchise anchor.'),
         ('All-Star', 1500, 'Recognized across the league as premium talent.'),
         ('Superstar', 1600, 'A generational talent and MVP contender.'),
         ('Hall of Fame', 1700, 'Legendary, immortalized status.'))
UNRANKED = 'Unranked'


def expected(rating, other):
    """The chance `rating` beats `other`."""
    return 1.0 / (1.0 + 10 ** ((other - rating) / SCALE))


def margin(goal_diff):
    return min(MARGIN_MAX, 1.0 + MARGIN_STEP * (max(1, goal_diff) - 1))


def tier(rating, games):
    """{name, index, placing}: `index` is the position in TIERS (None while unranked), `placing` the rated games to go."""
    if games < PLACEMENT:
        return {'name': UNRANKED, 'index': None, 'placing': PLACEMENT - games}
    idx = max(i for i, (_, low, _blurb) in enumerate(TIERS) if rating >= low)
    return {'name': TIERS[idx][0], 'index': idx, 'placing': 0}


def _blank(name):
    return {'name': name, 'rating': START, 'games': 0, 'w': 0, 'l': 0, 'streak': 0, 'peak': START, 'last': None}


def rate(matches, season_start=0.0):
    """Fold the confirmed, un-voided matches of this season in time order.

    Returns {ratings: {pid: {name, rating, games, w, l, streak, peak, last}},
             deltas: {match_id: {pid: {before, after, delta, expected, weight}}},
             timeline: {pid: [(started, match_id, rating after)]}}.
    `games` counts rated games (a fully damped game is a result but not a rated game); `streak` is wins (+) or losses (-)
    in a row over every confirmed result."""
    state, deltas, timeline, pair_times = {}, {}, {}, {}
    order = sorted((m for m in matches if not m.get('voided') and m['started'] >= season_start),
                   key=lambda m: (m['started'], m['id']))
    for m in order:
        res = H.resolve(m)
        for p in m['players']:                                  # newest name wins (the order is oldest first)
            state.setdefault(p['pid'], _blank(p['name']))['name'] = p['name']
        if res['status'] != H.CONFIRMED:
            continue
        a, b = (p['pid'] for p in m['players'])
        sa, sb = res['scores'][a], res['scores'][b]
        pair = tuple(sorted((a, b)))
        seen = [t for t in pair_times.setdefault(pair, []) if m['started'] - t < PAIR_WINDOW]
        weight = PAIR_WEIGHTS[min(len(seen), len(PAIR_WEIGHTS) - 1)]
        pair_times[pair] = seen + [m['started']]
        ra, rb = state[a]['rating'], state[b]['rating']
        mult = margin(abs(sa - sb))
        got = {}
        for me, other, won, r_me, r_other in ((a, b, sa > sb, ra, rb), (b, a, sb > sa, rb, ra)):
            row = state[me]
            exp = expected(r_me, r_other)
            k = K_NEW if row['games'] < K_GAMES else K_SETTLED
            delta = k * mult * weight * ((1.0 if won else 0.0) - exp)
            got[me] = {'before': r_me, 'after': r_me + delta, 'delta': delta, 'expected': exp, 'weight': weight}
        for me, won in ((a, sa > sb), (b, sb > sa)):
            row = state[me]
            row['rating'] = got[me]['after']
            row['peak'] = max(row['peak'], row['rating'])
            row['w' if won else 'l'] += 1
            row['games'] += 1 if weight > 0 else 0
            row['streak'] = (max(row['streak'], 0) + 1) if won else (min(row['streak'], 0) - 1)
            row['last'] = m['started']
            timeline.setdefault(me, []).append((m['started'], m['id'], row['rating']))
        deltas[m['id']] = got
    return {'ratings': state, 'deltas': deltas, 'timeline': timeline}
