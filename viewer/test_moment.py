"""The scoring touch inside a key moment."""

import math

import watch

assert watch._scoring_clock([
    {'action': 'PASS', 'clock': '11:20'},
    {'action': 'SHOT', 'clock': '12:08'},
    {'action': 'GOAL', 'clock': '12:11'},
], 671, 731) == (12 * 60 + 8, 12 * 60 + 11)

assert watch._scoring_clock([
    {'action': 'SHOT', 'clock': '12:08'},
    {'action': 'GOAL', 'clock': '12:11'},
    {'action': 'SHOT', 'clock': '12:40'},
], 671, 760) == (12 * 60 + 8, 12 * 60 + 11)

assert watch._scoring_clock([
    {'action': 'OWN GOAL', 'clock': '40:20'},
], 2360, 2420) == (None, 2420)

assert watch._moment_beats([
    {'team': 0, 'shirt': 10, 'action': 'SHORT PASS', 'clock': '11:40'},
    {'team': 0, 'shirt': 9, 'action': 'CONTROL', 'clock': '12:02'},
    {'team': 0, 'shirt': 9, 'action': 'SHOT', 'clock': '12:08'},
    {'team': 0, 'shirt': 9, 'action': 'GOAL', 'clock': '12:11'},
], 671, 731) == (11 * 60 + 39, 12 * 60 + 7, 12 * 60 + 11)

assert watch._moment_beats([
    {'team': 0, 'shirt': 8, 'action': 'SHORT PASS', 'clock': '11:20'},
    {'team': 0, 'shirt': 6, 'action': 'CONTROL', 'clock': '11:30'},
    {'team': 0, 'shirt': 6, 'action': 'SHORT PASS', 'clock': '11:40'},
    {'team': 0, 'shirt': 9, 'action': 'TRAP', 'clock': '12:02'},
    {'team': 0, 'shirt': 9, 'action': 'SHOT', 'clock': '12:08'},
    {'team': 0, 'shirt': 9, 'action': 'GOAL', 'clock': '12:11'},
], 671, 731) == (11 * 60 + 39, 12 * 60 + 7, 12 * 60 + 11)

assert watch._moment_beats([
    {'team': 0, 'shirt': 9, 'action': 'SHORT PASS', 'clock': '11:40'},
    {'team': 1, 'shirt': 2, 'action': 'CONTROL', 'clock': '11:50'},
    {'team': 0, 'shirt': 8, 'action': 'SHOT', 'clock': '12:08'},
    {'team': 0, 'shirt': 8, 'action': 'GOAL', 'clock': '12:11'},
], 671, 731) == (12 * 60 + 8, 12 * 60 + 7, 12 * 60 + 11)

x, y, z = watch._pitch_meters(55.3 / 54.4, 3.3 / -83.6, 0.4)
assert abs(x - 55.3) < 1e-6
assert abs(y - 3.3) < 1e-6
assert z == 0.4
delta = watch._pose_delta((0.0, 0.0, 5.0, 0.1, -0.2), (1.0, 0.0, 5.0, 0.3 - 2.0 * math.pi, -0.2))
assert abs(delta[0] - 1.0) < 1e-6
assert abs(delta[3] - 0.2) < 1e-6
moved = watch._step_pose((99.0, 0.0, 0.5, 0.0, 0.0), (50.0, 0.0, -5.0, 0.0, 0.0), 1.0)
assert moved[0] == 100.0 and moved[2] == 0.4
assert watch._defending_side([
    {'action': 'GOAL', 'clock': '12:11', 'team': 0},
], 0, 800) == 1
assert watch._defending_side([
    {'action': 'OWN GOAL', 'clock': '12:11', 'team': 1},
], 0, 800) == 1
assert watch._fullback_indexes([0, 1, 2, 1, 3, 5]) == [2, 4]
assert watch._fullback_indexes([0, 1, 5]) == []
assert watch._scorer_identity([
    {'action': 'GOAL', 'clock': '12:11', 'team': 0, 'shirt': 9},
], 0, 800) == (0, 9)
assert watch._scoring_touch(10, 12, 0.1, None) == (False, None)
assert watch._scoring_touch(11, 12, 1.0, None) == (False, 1.0)
assert watch._scoring_touch(11, 12, 0.5, 1.0) == (False, 0.5)
assert watch._scoring_touch(11, 12, 0.56, 0.5)[0]
assert not watch._scoring_touch(11, 12, 1.3, 1.1)[0]
assert watch._scoring_touch(11, 12, 0.2, None) == (True, 0.2)
assert watch._scoring_touch(12, 12, 6.0, None) == (False, 6.0)
ordered = watch._order_fullbacks([
    {'x': 10.0, 'y': 0.0, 'player': 2},
    {'x': 0.0, 'y': 0.0, 'player': 4},
], (1.0, 0.0, 0.2))
assert [mark['player'] for mark in ordered] == [4, 2]
aimed = watch._focus_distance([0.0, -20.0, 8.0, 1.2, -0.4])
assert aimed > 1.0
assert watch._focus_distance([0.0, 0.0, 5.0, 0.0, 0.1]) == 0.0
assert watch._ball_reset(55.4, 0.0)
assert not watch._ball_reset(42.0, 44.0)
assert not watch._ball_reset(55.4, 56.2)

assert watch._possession_share([], '00:00') == [50, 50]
assert watch._possession_share([
    {'team': 0, 'clock': '00:10'},
], '01:00') == [100, 0]
assert watch._possession_share([
    {'team': 0, 'clock': '00:00'},
    {'team': 1, 'clock': '00:20'},
], '01:00') == [33, 67]
assert watch._possession_share([
    {'team': 0, 'clock': '00:00'},
    {'team': 1, 'clock': '02:00'},
], '01:00') == [100, 0]
assert watch._possession_share([
    {'team': 0, 'clock': '00:10'},
    {'team': 1, 'clock': '00:10'},
], '00:20') == [0, 100]

assert watch._picture_size(1280 * 720) == (1280, 720)
assert watch._picture_size(1920 * 1080) == (1920, 1080)
assert watch._picture_size(2560 * 1360) == (2560, 1360)
assert watch._picture_size(0) is None
assert watch._frame_repeats(1.0 / 70.0) == 1
assert watch._frame_repeats(1.0 / 30.0) == 2
assert watch._frame_repeats(1.0 / 12.0) == 5
assert watch._frame_repeats(3.5) == 210

percent, goal = watch.moment_load_percent(0, 1000)
assert percent == 0 and goal == 1000
percent, goal = watch.moment_load_percent(500, 1000)
assert percent == 49 and goal == 1000
shown, goal = 0, 1000
last = 0
for written in range(0, 4000, 25):
  shown, goal = watch.moment_load_percent(written, goal, shown)
  assert last <= shown <= 99
  last = shown
assert last >= 90
assert watch._moment_frame_goal(0, 60) > watch.broadcast.OPEN_FRAMES

goal = watch.compare_load_goal(300, 300)
title = watch.broadcast.OPEN_FRAMES + watch.broadcast.COMPARE_HOLD
side_by_side = 300 * 2
assert goal > 600 + title + side_by_side
percent, _ = watch.moment_load_percent(600, goal)
assert percent < 50
percent, _ = watch.moment_load_percent(600 + title, goal)
assert percent < 70
plain = watch.compare_load_goal(300, 300)
with_look = watch.compare_load_goal(300 + 180, 300 + 180, 180)
assert with_look - plain == 180 * 2 + 180

def row(ball, owner, score):
  return {'ball': ball, 'owner': owner, 'score': score}

same = [row((0, 0), (0, 1), (0, 0)) for _ in range(30)]
split = [dict(item) for item in same]
split[12] = row((6, 0), (1, 4), (0, 0))
for index in range(13, 30):
  split[index] = row((6, 0), (1, 4), (0, 0))
assert watch.compare_beats(same, split) == [('split', 12)]
scored = [dict(item) for item in same]
scored[22] = row((40, 0), (0, 9), (1, 0))
assert watch.compare_beats(scored, same) == [('chance', 22)]
close = [dict(item) for item in scored]
close[18] = row((5, 1), (1, 2), (0, 0))
assert watch.compare_beats(scored, close) == [('chance', 22)]
assert watch._compare_segments(10, [3], 2) == [('play', 4), ('look', 2), ('play', 6)]
assert watch._same_score((1, 0), (1, 0))
assert not watch._same_score((1, 0), (2, 0))
assert not watch._same_score((1, 0), (1, 1))

print('moment ok')
