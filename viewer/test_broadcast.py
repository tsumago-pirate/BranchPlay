"""The key-moment broadcast frame."""

import cv2
import numpy as np

import broadcast

assert broadcast.goal_minute(86 * 60 + 52) == 87
assert broadcast.goal_minute(5 * 60 + 32) == 6
assert broadcast.goal_minute(12 * 60 + 11) == 13
assert broadcast.goal_minute(0) == 1

assert broadcast.side_label('FRQ') == 'ARS'
assert broadcast.side_label('RBA') == 'MNC'
assert broadcast.side_label('ars') == 'ARS'

rows = [
    {'team': 0, 'shirt': 9, 'name': 'Curie', 'action': 'GOAL', 'clock': '05:32'},
    {'team': 0, 'shirt': 8, 'name': 'Euler', 'action': 'GOAL', 'clock': '35:15'},
]
early = broadcast.scorer_card(rows, 0, 6 * 60)
assert early['name'] == 'CURIE' and early['shirt'] == 9 and early['minute'] == 6
later = broadcast.scorer_card(rows, 30 * 60, 40 * 60)
assert later['name'] == 'EULER' and later['minute'] == 36
assert broadcast.scorer_card(rows, 0, 60) is None

pitch = np.zeros((720, 1280, 3), np.uint8)
pitch[:] = (48, 140, 70)
cv2.rectangle(pitch, (80, 80), (1200, 640), (230, 230, 230), 2)
plate = broadcast.BroadcastPlate('FRQ', 'RBA', early)
plate.set_state(5 * 60 + 32, (1, 0), False)
def _league_ground(pixel):
  blue, green, red = int(pixel[0]), int(pixel[1]), int(pixel[2])
  magenta = blue > 60 and green < 30 and red > 180
  purple = 30 < blue < 90 and green < 30 and red < 90
  return magenta or purple

title = plate.stamp(pitch).copy()
later = plate.stamp(pitch).copy()
# The opening is a full-screen magenta and purple card, and the pattern moves.
assert _league_ground(title[8, 8])
assert _league_ground(title[360, 8])
assert _league_ground(title[700, 1200])
assert not np.array_equal(title[:120, :320], later[:120, :320])
for _ in range(broadcast.OPEN_IN - 2):
  plate.stamp(pitch)
held = plate.stamp(pitch).copy()
# White type sits in the middle once the title has arrived.
band = held[250:480, 200:1080]
white = (band[:, :, 0] > 230) & (band[:, :, 1] > 230) & (band[:, :, 2] > 230)
assert white.any()
for _ in range(broadcast.OPEN_FRAMES - broadcast.OPEN_IN - 1):
  plate.stamp(pitch)
opening = plate.stamp(pitch)
assert opening.shape == pitch.shape
# The title has opened onto the match. The corners stay on the pattern.
assert np.array_equal(opening[360, 640], pitch[360, 640])
assert not np.array_equal(opening[4, 4], pitch[4, 4])
corner = opening[:48, :48].copy()
full = opening
for _ in range(broadcast.SCORE_FRAMES):
  full = plate.stamp(pitch)
# The score block is the league green, which the pitch is not.
assert ((full[:, :, 1] > 220) & (full[:, :, 2] < 40)).any()
# The picture sits on the pattern. There is no cyan rule around it.
edge = full[360, 44]
assert not (int(edge[0]) > 240 and int(edge[1]) > 230 and int(edge[2]) < 30)
plate.set_state(5 * 60 + 32, (1, 0), True)
lower = full
for _ in range(max(broadcast.LOWER_FRAMES, 160)):
  lower = plate.stamp(pitch)
# The scorer's name plate is that same green, along the bottom.
bottom = lower[int(lower.shape[0] * 0.7):]
assert ((bottom[:, :, 1] > 220) & (bottom[:, :, 2] < 40)).any()
# The ribbons have moved by the time the lower bar is open.
assert not np.array_equal(corner, lower[:48, :48])
plate.begin_close()
closing = plate.stamp(pitch).copy()
# The way out starts as the match, with the title pattern taking the corners.
assert np.array_equal(closing[360, 640], pitch[360, 640])
assert _league_ground(closing[4, 4])
for _ in range(broadcast.CLOSE_IN):
  closing = plate.stamp(pitch)
held_out = closing.copy()
# Once the match has closed, the full-screen title is back.
assert _league_ground(held_out[8, 8])
assert _league_ground(held_out[700, 1200])
band = held_out[250:480, 200:1080]
white = (band[:, :, 0] > 230) & (band[:, :, 1] > 230) & (band[:, :, 2] > 230)
assert white.any()
def _green_purple(pixel):
  blue, green, red = int(pixel[0]), int(pixel[1]), int(pixel[2])
  # Green is #00FF85. Purple is #38003C. Magenta is not this card.
  field = green > 220 and red < 40
  purple = 30 < blue < 90 and green < 30 and red < 90
  magenta = blue > 60 and green < 30 and red > 180
  return (field or purple) and not magenta


def _white_span(image):
  white = (image[:, :, 0] > 230) & (image[:, :, 1] > 230) & (image[:, :, 2] > 230)
  rows = np.where(white.any(axis=1))[0]
  if len(rows) == 0:
    return 0
  return int(rows[-1] - rows[0])


left = np.zeros((720, 1280, 3), np.uint8)
left[:] = (20, 40, 220)
right = np.zeros_like(left)
right[:] = (220, 30, 20)
compare = broadcast.ComparePlate('FRQ', 'RBA', 12)
compare.set_state(12 * 60 + 11, (1, 0), (1, 0))
opening = compare.stamp(left, right).copy()
assert _green_purple(opening[8, 8])
assert _green_purple(opening[700, 1200])
assert not _league_ground(opening[8, 8]) or _green_purple(opening[8, 8])
moved = compare.stamp(left, right).copy()
assert not np.array_equal(opening[:80, :80], moved[:80, :80])
for _ in range(broadcast.OPEN_IN - 2):
  compare.stamp(left, right)
titled = compare.stamp(left, right).copy()
assert _white_span(titled) > 20
for _ in range(broadcast.OPEN_FRAMES):
  compare.stamp(left, right)
split = compare.stamp(left, right).copy()
left_half = split[:, :split.shape[1] // 2]
right_half = split[:, split.shape[1] // 2:]
assert np.any(np.all(left_half == left[0, 0], axis=2))
assert np.any(np.all(right_half == right[0, 0], axis=2))
assert not np.any(np.all(left_half == right[0, 0], axis=2))
assert _green_purple(split[4, 4])
open_span = _white_span(titled)
compare.set_state(12 * 60 + 11, (1, 0), (0, 0))
compare.begin_close()
for _ in range(broadcast.CLOSE_IN):
  compare.stamp(left, right)
outro = compare.stamp(left, right).copy()
assert _green_purple(outro[8, 8])
assert _green_purple(outro[360, 640])
assert _white_span(outro) > open_span

english = broadcast.BroadcastPlate('FRQ', 'RBA', early, 'en')
spanish = broadcast.BroadcastPlate('FRQ', 'RBA', early, 'es')
en_title = english.stamp(pitch)
es_title = spanish.stamp(pitch)
for _ in range(broadcast.OPEN_IN):
  en_title = english.stamp(pitch)
  es_title = spanish.stamp(pitch)
assert not np.array_equal(en_title, es_title)

print('broadcast ok')
