"""Move one team, or both, into a named shape.

The numbers are the outfield lines, goalkeeper included in the eleven.
Coordinates are the engine's formation space: x is -1 at a team's own goal
and +1 at the goal they attack, y is +1 on their left. The outfield dots
are the mplsoccer formation table (the same slots StatsBomb, Opta, and
Wyscout use), scaled from that library's 120 by 80 pitch. The goalkeeper
stays on the goal line. The engine places the outfield with the kickoff
standing-up formula, not across the whole pitch.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import re

# Pitch halves, in metres. A placed shape uses the same standing-up formula
# as the engine's kickoff: six tenths of each half, then the length is
# halved again and shifted toward that team's own goal. The goalkeeper
# stands on the goal line. apply_formation in the engine uses these same
# numbers. Stretching a shape across the whole pitch pulls the lines apart
# until it no longer reads as that formation.
PITCH_HALF_W = 55.0
PITCH_HALF_H = 36.0
DEPTH_FACTOR = 0.6
WIDTH_FACTOR = 0.6
X_COMPRESS = 0.5
X_OWN_SHIFT = 0.2
GK_LINE = 0.98

ROLES = {
    'GK': 0,
    'CB': 1,
    'LB': 2,
    'RB': 3,
    'DM': 4,
    'CM': 5,
    'LM': 6,
    'RM': 7,
    'AM': 8,
    'CF': 9,
}

_DISPLAY = {'FRQ': 'ARS', 'RBA': 'MNC'}

_SHAPE_ORDER = (
    '3-4-2-1',
    '4-2-3-1',
    '4-3-3',
    '4-4-2',
    '3-5-2',
    '4-5-1',
)


def _slot(role, x, y):
  return {'role': ROLES[role], 'x': float(x), 'y': float(y)}


def _gk():
  return [_slot('GK', -1.0, 0.0)]


def _four():
  # mplsoccer line of four, on the StatsBomb 120 by 80 pitch at x=31.2.
  return [
      _slot('LB', -0.48, 0.75),
      _slot('CB', -0.48, 0.25),
      _slot('CB', -0.48, -0.25),
      _slot('RB', -0.48, -0.75),
  ]


def _three():
  # mplsoccer line of five, the three centre backs, at x=31.2.
  return [
      _slot('CB', -0.48, 0.40),
      _slot('CB', -0.48, 0.0),
      _slot('CB', -0.48, -0.40),
  ]


FORMATIONS = {
    # mplsoccer '433': flat back four, one holder, two eights, two wingers, striker.
    '4-3-3': _gk() + _four() + [
        _slot('DM', -0.16, 0.0),
        _slot('CM', 0.16, 0.40),
        _slot('CM', 0.16, -0.40),
        _slot('LM', 0.48, 0.80),
        _slot('CF', 0.80, 0.0),
        _slot('RM', 0.48, -0.80),
    ],
    # mplsoccer '4231': two holders, a line of three, one striker.
    '4-2-3-1': _gk() + _four() + [
        _slot('DM', -0.16, 0.40),
        _slot('DM', -0.16, -0.40),
        _slot('LM', 0.48, 0.80),
        _slot('AM', 0.48, 0.0),
        _slot('RM', 0.48, -0.80),
        _slot('CF', 0.80, 0.0),
    ],
    # mplsoccer '442': flat back four, flat midfield four, two strikers.
    '4-4-2': _gk() + _four() + [
        _slot('LM', 0.16, 0.75),
        _slot('CM', 0.16, 0.25),
        _slot('CM', 0.16, -0.25),
        _slot('RM', 0.16, -0.75),
        _slot('CF', 0.80, 0.25),
        _slot('CF', 0.80, -0.25),
    ],
    # mplsoccer '352': three centre backs, wing-backs, three midfielders, two strikers.
    '3-5-2': _gk() + _three() + [
        _slot('LM', -0.16, 0.80),
        _slot('RM', -0.16, -0.80),
        _slot('CM', 0.16, 0.40),
        _slot('CM', 0.16, 0.0),
        _slot('CM', 0.16, -0.40),
        _slot('CF', 0.80, 0.25),
        _slot('CF', 0.80, -0.25),
    ],
    # mplsoccer '3421': three centre backs, a flat four, two attacking midfielders, one striker.
    '3-4-2-1': _gk() + _three() + [
        _slot('LM', -0.16, 0.75),
        _slot('DM', -0.16, 0.25),
        _slot('DM', -0.16, -0.25),
        _slot('RM', -0.16, -0.75),
        _slot('AM', 0.48, 0.25),
        _slot('AM', 0.48, -0.25),
        _slot('CF', 0.80, 0.0),
    ],
    # mplsoccer '451': back four, five across the middle, one striker.
    '4-5-1': _gk() + _four() + [
        _slot('LM', 0.16, 0.80),
        _slot('CM', 0.16, 0.40),
        _slot('CM', 0.16, 0.0),
        _slot('CM', 0.16, -0.40),
        _slot('RM', 0.16, -0.80),
        _slot('CF', 0.80, 0.0),
    ],
}

# How many outfield players stand in each line, goalkeeper not included.
# The order is own goal first.
LINE_COUNTS = {
    '4-3-3': (4, 3, 3),
    '4-2-3-1': (4, 2, 3, 1),
    '4-4-2': (4, 4, 2),
    '3-5-2': (3, 5, 2),
    '3-4-2-1': (3, 4, 2, 1),
    '4-5-1': (4, 5, 1),
}

SHAPE_LIST = ', '.join(_SHAPE_ORDER)


def slots(name):
  """The eleven roles and coordinates for one named shape. None if unnamed."""
  rows = FORMATIONS.get(str(name or ''))
  if not rows:
    return None
  return [dict(row) for row in rows]


def _side(side):
  return -1.0 if float(side) < 0 else 1.0


def slot_to_world(x, y, side, keeper=False):
  """Metres on the pitch for one formation slot.

  side is the engine's dynamic side. -1 defends the negative touchline.
  The same formula is in apply_formation.
  """
  side = _side(side)
  if keeper:
    return (side * PITCH_HALF_W * GK_LINE, 0.0)
  depth = PITCH_HALF_W * DEPTH_FACTOR * X_COMPRESS
  width = PITCH_HALF_H * WIDTH_FACTOR
  return (
      -side * float(x) * depth + side * PITCH_HALF_W * X_OWN_SHIFT,
      -side * float(y) * width,
  )


def world_to_norm(x, y, side):
  """Formation coordinates for a world position on this team's side."""
  side = _side(side)
  depth = PITCH_HALF_W * DEPTH_FACTOR * X_COMPRESS
  width = PITCH_HALF_H * WIDTH_FACTOR
  along = float(x) - side * PITCH_HALF_W * X_OWN_SHIFT
  return (-side * along / depth, -side * float(y) / width)


def attack_points(name, side=-1):
  """Each slot as (depth, width) metres. Depth grows away from the own goal."""
  rows = slots(name)
  if not rows:
    return []
  points = []
  for index, row in enumerate(rows):
    px, py = slot_to_world(
        row['x'], row['y'], side, keeper=(index == 0))
    side_sign = _side(side)
    depth = -side_sign * px
    width = -side_sign * py
    points.append((depth, width))
  return points


def pitch_shape(name, players, played=False):
  """None when these pitch positions read as the named shape.

  players are (depth, width) in metres. Depth grows toward the goal this
  team is attacking. The goalkeeper is the player nearest their own goal.
  A line that is piled onto the one behind it, or left a whole half away
  from it, is not that shape. Once the match is moving, a line may tuck
  in a little. played allows that. It does not allow the lines to split
  the length of the pitch.
  """
  counts = LINE_COUNTS.get(name)
  if not counts:
    return 'unknown shape'
  if len(players) != 11:
    return 'expected 11 players'
  ordered = sorted(players, key=lambda point: point[0])
  keeper = ordered[0]
  outfield = ordered[1:]
  groups = []
  cursor = 0
  for count in counts:
    groups.append(outfield[cursor:cursor + count])
    cursor += count
  reasons = []
  previous = None
  for index, group in enumerate(groups):
    depths = [point[0] for point in group]
    widths = [point[1] for point in group]
    span = max(depths) - min(depths)
    if span > (24.0 if played else 14.0):
      reasons.append('line %d is %.0fm deep' % (index + 1, span))
    mean = sum(depths) / float(len(depths))
    if previous is not None:
      gap = mean - previous
      if gap < 4.0:
        reasons.append('line %d is on the line behind it' % (index + 1))
      if gap > (22.0 if played else 18.0):
        reasons.append('line %d is %.0fm clear of the line behind it' % (
            index + 1, gap))
    previous = mean
    wide = max(widths) - min(widths)
    if played:
      wide_5, wide_4, wide_3, wide_2 = 16.0, 14.0, 8.0, 4.0
    else:
      wide_5, wide_4, wide_3, wide_2 = 28.0, 24.0, 16.0, 6.0
    if len(group) >= 5 and wide < wide_5:
      reasons.append('line %d is only %.0fm wide' % (index + 1, wide))
    elif len(group) == 4 and wide < wide_4:
      reasons.append('line %d is only %.0fm wide' % (index + 1, wide))
    elif len(group) == 3 and wide < wide_3:
      reasons.append('line %d is only %.0fm wide' % (index + 1, wide))
    elif len(group) == 2 and wide < wide_2:
      reasons.append('a pair is only %.0fm apart' % wide)
    if len(group) >= 3 and abs(sum(widths) / float(len(widths))) > 8.0:
      reasons.append('line %d is shifted to one side' % (index + 1))
  back = sum(point[0] for point in groups[0]) / float(len(groups[0]))
  if back - keeper[0] < 18.0:
    reasons.append('the goalkeeper is in the back line')
  return '; '.join(reasons) if reasons else None


def assign(shape, players, side):
  """Give each active player a slot. The goalkeeper stays the goalkeeper.

  Outfield slots go to the nearest player in formation space. A sent-off
  player is left out. The list is shorter than eleven when the side is.
  """
  wanted = slots(shape)
  if not wanted:
    return []
  active = []
  for player in players or []:
    if not isinstance(player, dict):
      continue
    if player.get('active') is False:
      continue
    try:
      active.append({
          'player': int(player['player']),
          'x': float(player['x']),
          'y': float(player['y']),
          'role': player.get('role'),
      })
    except (TypeError, ValueError, KeyError):
      continue
  if not active:
    return []
  keeper_slot = None
  outfield = []
  for row in wanted:
    if int(row['role']) == ROLES['GK'] and keeper_slot is None:
      keeper_slot = row
    else:
      outfield.append(row)
  keeper = None
  for player in active:
    if player['role'] in ('GK', ROLES['GK'], '0'):
      keeper = player
      break
  if keeper is None:
    keeper = min(active, key=lambda player: world_to_norm(
        player['x'], player['y'], side)[0])
  chosen = []
  used = set()
  if keeper_slot is not None:
    chosen.append({
        'player': keeper['player'],
        'role': ROLES['GK'],
        'x': float(keeper_slot['x']),
        'y': float(keeper_slot['y']),
    })
    used.add(keeper['player'])
  rest = [player for player in active if player['player'] not in used]
  pairs = []
  located = []
  for player in rest:
    nx, ny = world_to_norm(player['x'], player['y'], side)
    located.append((player, nx, ny))
  for index, row in enumerate(outfield):
    for player, nx, ny in located:
      dist = (nx - row['x']) ** 2 + (ny - row['y']) ** 2
      pairs.append((dist, player['player'], index))
  pairs.sort()
  taken_slots = set()
  taken_players = set()
  for _dist, player_index, slot_index in pairs:
    if player_index in taken_players or slot_index in taken_slots:
      continue
    taken_players.add(player_index)
    taken_slots.add(slot_index)
    row = outfield[slot_index]
    chosen.append({
        'player': player_index,
        'role': int(row['role']),
        'x': float(row['x']),
        'y': float(row['y']),
    })
    if len(taken_players) == len(rest) or len(taken_slots) == len(outfield):
      break
  return chosen


def pack_entries(rows):
  """A formation read back from the engine, safe to store and apply again."""
  packed = []
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    try:
      role = int(row['role'])
      packed.append({
          'player': int(row['player']),
          'role': role,
          'x': round(float(row['x']), 4),
          'y': round(float(row['y']), 4),
      })
    except (TypeError, ValueError, KeyError):
      continue
    if role < 0 or role > ROLES['CF']:
      packed.pop()
  return packed


def _normalize(question):
  raw = str(question or '').lower().replace('–', '-').replace('—', '-')
  return ' ' + re.sub(r'[^a-z0-9\-]+', ' ', raw) + ' '


def _shapes_in(text):
  pattern = '|'.join(name.replace('-', r'\s*-\s*') for name in _SHAPE_ORDER)
  found = []
  for match in re.finditer(
      r'(?<![\d\-])(?:%s)(?![\d\-])' % pattern, text):
    name = re.sub(r'\s+', '', match.group(0))
    found.append((match.start(), match.end(), name))
  return found


def _is_command(text):
  if re.search(
      r'\b(?:move|put|switch|change|set|shift|send|place|drop|use|make)\b', text):
    return True
  return bool(re.search(r'\b(?:in|into)\s+(?:a\s+)?\d', text))


def _side_name(snapshot, team):
  key = 'left_name' if int(team) == 0 else 'right_name'
  raw = str((snapshot or {}).get(key) or '').strip()
  if not raw:
    return 'Left' if int(team) == 0 else 'Right'
  return _DISPLAY.get(raw, raw)


def _mentions(text, snapshot):
  """Team names and both, in the order they are written."""
  import match_chat
  candidates = []
  for match in re.finditer(r'\bboth(?:\s+teams|\s+sides)?\b', text):
    candidates.append((match.start(), match.end(), 'both'))
  for pattern, side in (
      (r'\bleft(?:\s+team|\s+side)?\b|\bthe left\b|\bon the left\b', 0),
      (r'\bright(?:\s+team|\s+side)?\b|\bthe right\b|\bon the right\b', 1),
  ):
    for match in re.finditer(pattern, text):
      after = text[match.end():match.end() + 16]
      if re.match(r'\s+(?:back|backs|mid|wing|forward|winger)\b', after):
        continue
      candidates.append((match.start(), match.end(), side))
  named = []
  for raw, side in (
      ((snapshot or {}).get('left_name') or 'FRQ', 0),
      ((snapshot or {}).get('right_name') or 'RBA', 1),
  ):
    label = _DISPLAY.get(str(raw).strip(), str(raw).strip()).upper()
    for phrase in match_chat.CLUB_NAMES.get(label, (label.lower(),)):
      named.append((phrase, side))
  named.sort(key=lambda item: len(item[0]), reverse=True)
  occupied = [(start, end) for start, end, _side in candidates]
  for phrase, side in named:
    for match in re.finditer(r'\b%s\b' % re.escape(phrase), text):
      span = match.span()
      if any(not (span[1] <= start or span[0] >= end) for start, end in occupied):
        continue
      candidates.append((span[0], span[1], side))
      occupied.append(span)
  candidates.sort(key=lambda item: (item[0], item[1] - item[0]))
  return [(start, end, side) for start, end, side in candidates]


def _reply(snapshot, sides):
  clock = str((snapshot or {}).get('clock') or '').strip() or '0:00'
  if sides.get(0) and sides.get(1) and sides[0] == sides[1]:
    return 'Both teams to %s from %s.' % (sides[0], clock)
  parts = []
  for team in (0, 1):
    if team in sides:
      parts.append('%s to %s' % (_side_name(snapshot, team), sides[team]))
  if len(parts) == 1:
    body = parts[0]
  else:
    body = '%s and %s' % (parts[0], parts[1])
  return '%s from %s.' % (body, clock)


def formation_from_question(question, snapshot=None):
  """A formation command, or None when the sentence is not one.

  sides maps team 0 and team 1 to a shape name. It is omitted when the
  sentence asks for a shape this match cannot play, or names no team.
  """
  text = _normalize(question)
  if not _is_command(text):
    return None
  shapes = _shapes_in(text)
  shape_like = re.search(r'(?<![\d\-])\d(?:\s*-\s*\d){2,4}(?![\d\-])', text)
  if not shapes:
    if shape_like or re.search(r'\bformations?\b', text):
      return {
          'text': 'The shapes are %s.' % SHAPE_LIST,
          'sides': None,
      }
    return None
  mentions = _mentions(text, snapshot)
  both = any(side == 'both' for _start, _end, side in mentions)
  teams = []
  for _start, _end, side in mentions:
    if side == 'both' or side in teams:
      continue
    teams.append(side)
  sides = {}
  if both and len(shapes) >= 2:
    sides[0] = shapes[0][2]
    sides[1] = shapes[1][2]
  elif both:
    sides[0] = shapes[0][2]
    sides[1] = shapes[0][2]
  elif len(teams) >= 2 and len(shapes) >= 2:
    sides[teams[0]] = shapes[0][2]
    sides[teams[1]] = shapes[1][2]
  elif len(teams) >= 1 and len(shapes) >= 2:
    return {
        'text': 'Say one shape for %s.' % _side_name(snapshot, teams[0]),
        'sides': None,
    }
  elif len(teams) >= 1:
    for team in teams:
      sides[team] = shapes[0][2]
  else:
    return {'text': 'Say which team, or both.', 'sides': None}
  return {'text': _reply(snapshot, sides), 'sides': sides}
