"""Elo rating and rank tiers (overtime_core.rating): known values, damping, margin, tiers, replay, and a simulation."""
import random

import pytest

from overtime_core import rating as R

DAY = 24 * 3600


def mk(mid, a, b, sa, sb, started, voided=False):
    """A confirmed match: a (pid, name) scored sa, b scored sb, both claims mirror."""
    m = {'id': mid, 'started': float(started), 'code': None, 'rules': None, 'voided': voided,
         'players': [{'pid': a[0], 'name': a[1]}, {'pid': b[0], 'name': b[1]}],
         'claims': {a[0]: {'team': 'SEA', 'opp_team': 'UTA', 'for': sa, 'against': sb, 'source': 'app'},
                    b[0]: {'team': 'UTA', 'opp_team': 'SEA', 'for': sb, 'against': sa, 'source': 'app'}}}
    return m


ANN, BO, CY = ('a1', 'Ann'), ('b2', 'Bo'), ('c3', 'Cy')


def test_expected_is_a_probability_and_half_for_equals():
    assert R.expected(1200, 1200) == pytest.approx(0.5)
    assert R.expected(1600, 1200) == pytest.approx(10 / 11)
    assert R.expected(1200, 1600) + R.expected(1600, 1200) == pytest.approx(1.0)


def test_first_game_between_new_players_moves_k_new_over_two_for_a_one_goal_win():
    out = R.rate([mk(1, ANN, BO, 3, 2, 1000)])
    ann, bo = out['ratings']['a1'], out['ratings']['b2']
    assert ann['rating'] == pytest.approx(R.START + R.K_NEW * 0.5)
    assert bo['rating'] == pytest.approx(R.START - R.K_NEW * 0.5)
    d = out['deltas'][1]['a1']
    assert d['before'] == R.START and d['expected'] == pytest.approx(0.5) and d['weight'] == 1.0
    assert (ann['w'], ann['l'], ann['streak'], bo['streak']) == (1, 0, 1, -1)


def test_margin_grows_with_goals_and_is_capped():
    assert R.margin(1) == 1.0 and R.margin(2) == pytest.approx(1.1)
    assert R.margin(6) == pytest.approx(1.5) and R.margin(40) == R.MARGIN_MAX
    big = R.rate([mk(1, ANN, BO, 7, 1, 1000)])['ratings']['a1']['rating']
    one = R.rate([mk(1, ANN, BO, 2, 1, 1000)])['ratings']['a1']['rating']
    assert big - R.START == pytest.approx(1.5 * (one - R.START))


def test_an_upset_pays_more_than_an_expected_win():
    games = [mk(i, ANN, CY, 3, 1, 1000 + i * 3 * DAY) for i in range(1, 8)]          # Ann becomes the favourite
    games.append(mk(20, CY, ANN, 3, 2, 1000 + 40 * DAY))                              # Cy upsets her
    games.append(mk(21, ANN, CY, 3, 2, 1000 + 50 * DAY))                              # she wins as the favourite
    out = R.rate(games)
    upset, normal = out['deltas'][20]['c3'], out['deltas'][21]['a1']
    assert upset['expected'] < 0.5 < normal['expected']
    assert upset['delta'] > normal['delta']


def test_a_settled_player_moves_less_than_a_new_one():
    games = [mk(i, ANN, BO, 3, 2, 1000 + i * 2 * DAY) for i in range(1, R.K_GAMES + 1)]
    out = R.rate(games + [mk(99, ANN, CY, 2, 1, 1000 + 60 * DAY)])
    d_ann, d_cy = out['deltas'][99]['a1'], out['deltas'][99]['c3']
    assert d_ann['delta'] == pytest.approx(R.K_SETTLED * (1 - d_ann['expected']))
    assert d_cy['delta'] == pytest.approx(-R.K_NEW * d_cy['expected'])


def test_repeat_pair_is_damped_within_a_day_then_fresh_again():
    one_day = [mk(i, ANN, BO, 3, 2, 1000 + i * 600) for i in range(1, 7)]
    out = R.rate(one_day)
    weights = [out['deltas'][i]['a1']['weight'] for i in range(1, 7)]
    assert weights == [1.0, 1.0, 0.5, 0.25, 0.0, 0.0]
    assert out['ratings']['a1']['games'] == 4 and out['ratings']['a1']['w'] == 6        # a damped win is a result, not a rated game
    later = R.rate(one_day + [mk(9, ANN, BO, 3, 2, 1000 + 2 * DAY)])
    assert later['deltas'][9]['a1']['weight'] == 1.0


def test_only_confirmed_unvoided_matches_in_season_count():
    waiting = mk(1, ANN, BO, 3, 2, 1000)
    del waiting['claims']['b2']
    disputed = mk(2, ANN, BO, 3, 2, 2000)
    disputed['claims']['b2'] = {'team': 'UTA', 'opp_team': 'SEA', 'for': 5, 'against': 0, 'source': 'app'}
    voided = mk(3, ANN, BO, 3, 2, 3000, voided=True)
    old = mk(4, ANN, BO, 3, 2, 10.0)
    good = mk(5, ANN, BO, 3, 2, 5000)
    out = R.rate([waiting, disputed, voided, old, good], season_start=100.0)
    assert list(out['deltas']) == [5] and out['ratings']['a1']['games'] == 1


def test_replay_is_deterministic_and_input_order_does_not_matter():
    games = [mk(i, [ANN, BO, CY][i % 3], [ANN, BO, CY][(i + 1) % 3], 3, i % 2, 1000 + i * 4000) for i in range(1, 20)]
    shuffled = list(reversed(games))
    assert R.rate(games)['ratings'] == R.rate(shuffled)['ratings']


def test_a_players_newest_name_is_kept_and_streak_flips():
    out = R.rate([mk(1, ANN, BO, 3, 2, 1000), mk(2, ('a1', 'Annie'), BO, 1, 2, 90000), mk(3, ('a1', 'Annie'), BO, 0, 4, 99999)])
    ann = out['ratings']['a1']
    assert ann['name'] == 'Annie' and ann['streak'] == -2 and ann['peak'] > ann['rating']


def test_tiers_and_placement():
    assert R.tier(1500, 4) == {'name': 'Unranked', 'index': None, 'placing': 1}
    assert R.tier(R.START, 5)['name'] == 'Rookie'                       # a new player starts as a Rookie
    ladder = ((0, 'Minor League'), (999.9, 'Minor League'), (1000, 'Rookie'), (1099.9, 'Rookie'), (1100, 'Pro'),
              (1200, 'Top 6'), (1300, 'Alternate Captain'), (1400, 'Captain'), (1500, 'All-Star'), (1599, 'All-Star'),
              (1600, 'Superstar'), (1699, 'Superstar'), (1700, 'Hall of Fame'), (2500, 'Hall of Fame'))
    for rating, name in ladder:
        assert R.tier(rating, 9)['name'] == name
    assert [t[0] for t in R.TIERS] == ['Minor League', 'Rookie', 'Pro', 'Top 6', 'Alternate Captain', 'Captain', 'All-Star',
                                       'Superstar', 'Hall of Fame']
    assert all(t[2] for t in R.TIERS) and [t[1] for t in R.TIERS][1:] == list(range(1000, 1800, 100))


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0] * len(v)
        for pos, i in enumerate(order):
            out[i] = float(pos)
        return out
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return 1 - 6 * d2 / (n * (n * n - 1))


def test_simulation_rating_order_follows_latent_skill():
    """12 players of known strength play 400 noisy matches (a game is won with the Elo chance of the true strengths);
    the replayed ratings must rank them about as they really are."""
    rng = random.Random(19)
    skill = {f'p{i:02d}': 1000 + 60 * i for i in range(12)}          # 1000 .. 1660
    names = {p: (p, p.upper()) for p in skill}
    games, t = [], 1000.0
    for mid in range(1, 401):
        a, b = rng.sample(sorted(skill), 2)
        t += rng.choice((900, 3600, 3 * DAY))
        a_wins = rng.random() < R.expected(skill[a], skill[b])
        win, lose = rng.randint(2, 7), rng.randint(0, 1)
        games.append(mk(mid, names[a], names[b], *((win, lose) if a_wins else (lose, win)), t))
    ratings = R.rate(games)['ratings']
    order = sorted(skill)
    assert spearman([skill[p] for p in order], [ratings[p]['rating'] for p in order]) >= 0.8
