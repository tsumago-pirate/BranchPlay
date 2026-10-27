"""Answer questions about the running match.

This is the match chat. It is not the narration component, and it does not
call that model. A reply may use only the touch log, the score, the clock,
the ball, and the player list the caller supplies. Each player has one
record: who they are, where they are, and a count of every touch in the
log. A highlight searches that record. The engine then draws the existing
wire box on each match. Highlight key moments is separate: each goal becomes
a stretch of the timeline, from 60 seconds before that goal through the goal. A connect request draws a line between each pair of
players that same search finds, until the lines are cleared. A camera request uses the same record to pick a
player, then sets the view: perspective is that player's eyes, and follow
is the long lens on that player. A formation request places one team, or
both, in 4-3-3, 4-2-3-1, 4-4-2, 3-5-2, 3-4-2-1, or 4-5-1 and holds the
picture there. The match plays on when it is resumed. A later restart
does not put them back in that shape.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import re
import urllib.error
import urllib.request

import formations

MODEL = 'phi4-mini'
OLLAMA_CHAT = 'http://127.0.0.1:11434/api/chat'

# The scoreboard shows these abbreviations. The engine's own short names
# stay underneath.
DISPLAY_NAMES = {'FRQ': 'ARS', 'RBA': 'MNC'}

# Names a question can use for the side shown on the scoreboard.
CLUB_NAMES = {
    'ARS': ('schmarsenal', 'ars'),
    'MNC': ('schman city', 'schmen city', 'schman', 'schmen', 'mnc'),
}

ROLES = ('GK', 'CB', 'LB', 'RB', 'DM', 'CM', 'LM', 'RM', 'AM', 'CF')
# The third flag is whether the words already name a side, so a later
# "left" or "right" is not also read as the team.
_ROLE_PATTERNS = (
    (r'\bgoal ?keepers?\b|\bkeepers?\b|\bgoalies?\b|\bgk\b', 'GK', False),
    (r'\b(?:centre|center) ?backs?\b|\bcbs?\b', 'CB', False),
    (r'\bleft ?backs?\b|\blb\b', 'LB', True),
    (r'\bright ?backs?\b|\brb\b', 'RB', True),
    (r'\bdefensive ?mids?\b|\bdm\b', 'DM', False),
    (r'\battacking ?mids?\b|\bam\b', 'AM', False),
    (r'\bleft ?(?:mids?|wingers?)\b|\blm\b', 'LM', True),
    (r'\bright ?(?:mids?|wingers?)\b|\brm\b', 'RM', True),
    (r'\b(?:forwards?|strikers?|(?:centre|center) ?forwards?)\b|\bcf\b', 'CF', False),
    (r'\b(?:midfielders?|central ?mids?)\b|\bcm\b', 'CM', False),
)
_REFEREE = re.compile(r'\b(?:refs?|referees?)\b')
_FULLBACKS = re.compile(r'\bfull ?backs?\b')
_DEFENDERS = re.compile(r'\bdefenders?\b')
ZONES = ('own_half', 'attacking_half', 'wide', 'center', 'near_ball')
STATS = (
    'fastest',
    'slowest',
    'most_touches',
    'fewest_touches',
    'has_ball',
    'most_tired',
)

# own half and the attacking half are per team. Wide is outside 18m of the
# centre line. Center is the middle of the pitch. Near the ball is 12m.
WIDE_Y = 18.0
CENTER_X = 18.0
CENTER_Y = 12.0
NEAR_BALL = 12.0

# One column per touch the log can record. A pass count is the short, long,
# and high pass rows. The log does not say whether a teammate received it.
TOUCH_FIELDS = (
    'control',
    'trap',
    'short_pass',
    'long_pass',
    'high_pass',
    'header',
    'shot',
    'deflect',
    'catch',
)
ACTION_FIELDS = {
    'CONTROL': 'control',
    'TRAP': 'trap',
    'SHORT PASS': 'short_pass',
    'LONG PASS': 'long_pass',
    'HIGH PASS': 'high_pass',
    'HEADER': 'header',
    'SHOT': 'shot',
    'DEFLECT': 'deflect',
    'CATCH': 'catch',
}
RECORD_COLUMNS = (
    'touches',
) + TOUCH_FIELDS + (
    'passes',
    'completed_passes',
    'goal',
    'own_goal',
    'speed',
    'tired',
    'shirt',
    'dist',
    'x',
    'y',
)
SEARCH_FIELDS = {
    'control': 'dribbles|dribble|controls|control',
    'trap': 'traps|trap',
    'short_pass': 'short passes|short pass',
    'long_pass': 'long passes|long pass',
    'high_pass': 'high passes|high pass',
    'header': 'headers|header',
    'shot': 'shots|shot',
    'deflect': 'deflections|deflection|deflects|deflect',
    'catch': 'catches|catch',
    'completed_passes': 'completed passes|completed pass',
    'own_goal': 'own goals|own goal',
    'goal': 'goals|goal|scored|scoring|scores|score',
    'passes': 'passes|pass',
    'touches': 'touches|touch',
    'speed': 'meters per second|speed',
    'tired': 'fatigue|tired',
    'shirt': 'shirts|shirt|numbers|number|numbered',
    'dist': 'meters from the ball|metres from the ball|from the ball',
    'x': 'meters along|along the pitch',
    'y': 'meters across|across the pitch',
}


class MatchChatError(Exception):
  """Phi-4 mini did not return a reply."""


def display_name(raw, fallback):
  text = str(raw or '').strip()
  if not text:
    return fallback
  return DISPLAY_NAMES.get(text, text)


def touch_counts(log):
  counts = {}
  for row in log or []:
    key = (int(row['team']), int(row['shirt']))
    counts[key] = counts.get(key, 0) + 1
  return counts


def _blank_counts():
  counts = {'touches': 0, 'completed_passes': 0, 'goal': 0, 'own_goal': 0}
  for field in TOUCH_FIELDS:
    counts[field] = 0
  return counts


_PASS_ACTIONS = ('SHORT PASS', 'LONG PASS', 'HIGH PASS')


def tally(log):
  """Full-log counts and the latest touch, keyed by team and shirt.

  A pass is completed when the next event is a teammate other than the
  passer. A goal is the scorer's goal. An own goal is counted apart, so it
  does not add to that player's goals. Neither goal is a touch.
  """
  counts = {}
  last = {}
  rows = list(log or [])
  for index, row in enumerate(rows):
    try:
      key = (int(row['team']), int(row['shirt']))
    except (KeyError, TypeError, ValueError):
      continue
    action = str(row.get('action') or '').strip().upper()
    bucket = counts.setdefault(key, _blank_counts())
    if action == 'GOAL':
      bucket['goal'] += 1
      continue
    if action == 'OWN GOAL':
      bucket['own_goal'] += 1
      continue
    bucket['touches'] += 1
    field = ACTION_FIELDS.get(action)
    if field:
      bucket[field] += 1
    if action in _PASS_ACTIONS and index + 1 < len(rows):
      nxt = rows[index + 1]
      try:
        completed = (int(nxt['team']) == key[0] and int(nxt['shirt']) != key[1])
      except (KeyError, TypeError, ValueError):
        completed = False
      if completed:
        bucket['completed_passes'] += 1
    last[key] = (action.lower(), str(row.get('clock') or ''))
  return counts, last


def player_record(roster, log, ball=None):
  """One organized row per player. Counts come from the whole log."""
  counts, last = tally(log)
  rows = []
  for player in roster or []:
    row = dict(player)
    key = (int(row['team']), int(row['shirt']))
    bucket = counts.get(key, _blank_counts())
    for field, value in bucket.items():
      row[field] = int(value)
    row['passes'] = row['short_pass'] + row['long_pass'] + row['high_pass']
    action, clock = last.get(key, ('', ''))
    row['last_action'] = action
    row['last_clock'] = clock
    if ball and len(ball) >= 2:
      dx = float(row['x']) - float(ball[0])
      dy = float(row['y']) - float(ball[1])
      row['dist'] = round((dx * dx + dy * dy) ** 0.5, 1)
    else:
      row['dist'] = None
    rows.append(row)
  return rows


def _own_half(player):
  if player['team'] == 0:
    return player['x'] < 0
  return player['x'] > 0


def _attacking_half(player):
  if player['team'] == 0:
    return player['x'] > 0
  return player['x'] < 0


def _in_zone(player, zone, ball):
  if zone == 'own_half':
    return _own_half(player)
  if zone == 'attacking_half':
    return _attacking_half(player)
  if zone == 'wide':
    return abs(player['y']) > WIDE_Y
  if zone == 'center':
    return abs(player['x']) < CENTER_X and abs(player['y']) < CENTER_Y
  if zone == 'near_ball':
    if not ball:
      return False
    dx = player['x'] - ball[0]
    dy = player['y'] - ball[1]
    return (dx * dx + dy * dy) ** 0.5 <= NEAR_BALL
  return True


def _rank(rows, stat):
  if not rows or not stat:
    return rows
  if stat == 'has_ball':
    return [row for row in rows if row['ball']]
  if stat == 'fastest':
    return [max(rows, key=lambda row: row['speed'])]
  if stat == 'slowest':
    return [min(rows, key=lambda row: row['speed'])]
  if stat == 'most_touches':
    return [max(rows, key=lambda row: (row['touches'], -row['player']))]
  if stat == 'fewest_touches':
    return [min(rows, key=lambda row: (row['touches'], row['player']))]
  if stat == 'most_tired':
    return [max(rows, key=lambda row: row['tired'])]
  return rows


def _rank_record(rows, rank):
  """The players with the most or fewest of a column. n is how many."""
  if not rows or not isinstance(rank, dict):
    return rows
  field = rank.get('field')
  if field not in RECORD_COLUMNS:
    return []
  how = rank.get('how')
  try:
    count = int(rank.get('n') or 1)
  except (TypeError, ValueError):
    count = 1
  count = max(1, min(count, len(rows)))

  def value(row):
    raw = row.get(field)
    if raw is None:
      return 0.0
    try:
      return float(raw)
    except (TypeError, ValueError):
      return 0.0

  if how == 'most':
    ordered = sorted(rows, key=lambda row: (value(row), -row.get('player', 0)),
                     reverse=True)
    return ordered[:count]
  if how == 'fewest':
    ordered = sorted(rows, key=lambda row: (value(row), row.get('player', 0)))
    return ordered[:count]
  return []


def _matches_where(row, clause):
  field = clause.get('field')
  if field not in RECORD_COLUMNS:
    return False
  op = clause.get('op')
  if op == 'odd':
    return int(row.get('shirt') or 0) % 2 == 1
  if op == 'even':
    return int(row.get('shirt') or 0) % 2 == 0
  value = row.get(field)
  if value is None:
    return False
  try:
    have = float(value)
    want = float(clause.get('value'))
  except (TypeError, ValueError):
    return False
  if op == '>=':
    return have >= want
  if op == '<=':
    return have <= want
  if op == '>':
    return have > want
  if op == '<':
    return have < want
  if op == '==':
    return have == want
  return False


def select_players(roster, spec, ball=None):
  """Players the highlight filter names. An empty spec matches nobody.

  clear is handled by the caller. A rank such as fastest keeps one player
  from the players who already matched the other fields. A where list is
  a search over the player record, and every clause has to match.
  """
  if not isinstance(spec, dict):
    return []
  where = [clause for clause in (spec.get('where') or []) if isinstance(clause, dict)]
  rank = spec.get('rank') if _record_rank(spec.get('rank')) else None
  everyone = bool(spec.get('everyone'))
  roles = [role for role in (spec.get('roles') or []) if role in ROLES]
  narrowed = everyone or bool(where) or rank or bool(roles) or any(
      spec.get(key) not in (None, '', False)
      for key in ('team', 'role', 'zone', 'stat', 'shirt', 'name'))
  if not narrowed:
    return []
  rows = [row for row in roster or [] if row.get('active', True)]
  team = spec.get('team')
  if team == 'left':
    rows = [row for row in rows if row['team'] == 0]
  elif team == 'right':
    rows = [row for row in rows if row['team'] == 1]
  elif team not in (None, ''):
    return []
  role = spec.get('role')
  if roles:
    rows = [row for row in rows if row['role'] in roles]
  elif role:
    if role not in ROLES:
      return []
    rows = [row for row in rows if row['role'] == role]
  shirt = spec.get('shirt')
  if shirt is not None and shirt != '':
    try:
      number = int(shirt)
    except (TypeError, ValueError):
      return []
    rows = [row for row in rows if row['shirt'] == number]
  name = str(spec.get('name') or '').strip().lower()
  if name:
    exact = [row for row in rows if str(row['name']).lower() == name]
    rows = exact or [row for row in rows
                     if str(row['name']).lower().startswith(name)]
  zone = spec.get('zone')
  if zone:
    if zone not in ZONES:
      return []
    rows = [row for row in rows if _in_zone(row, zone, ball)]
  stat = spec.get('stat')
  if stat and stat not in STATS:
    return []
  for clause in where:
    rows = [row for row in rows if _matches_where(row, clause)]
  rows = _rank(rows, stat)
  if rank:
    rows = _rank_record(rows, rank)
    field = rank.get('field')
    if (rows and rank.get('how') == 'most' and
        field in set(TOUCH_FIELDS) | {
            'touches', 'passes', 'completed_passes', 'goal', 'own_goal'}):
      try:
        top = int(rows[0].get(field) or 0)
      except (TypeError, ValueError):
        top = 0
      if top <= 0:
        return []
  return rows


def describe_highlight(players, spec, left_name, right_name):
  if isinstance(spec, dict) and spec.get('clear'):
    return 'Boxes cleared.'
  if not players:
    return 'No player in the match matches that.'
  if isinstance(spec, dict) and spec.get('everyone'):
    return 'Boxed every player.'
  if len(players) > 2:
    return 'Boxed %s players.' % len(players)
  parts = []
  for player in players:
    side = left_name if player['team'] == 0 else right_name
    parts.append('%s %s %s' % (side, player['name'], player['shirt']))
  if len(parts) == 1:
    return 'Boxed %s.' % parts[0]
  return 'Boxed %s.' % ', '.join(parts)


def _touch_line(row, left_name, right_name):
  side = left_name if int(row['team']) == 0 else right_name
  action = str(row['action']).strip().lower()
  return '%s %s %s %s' % (row['clock'], side, row['shirt'], action)


def snapshot_text(snapshot):
  """The only facts the reply is allowed to use."""
  left = display_name(snapshot.get('left_name'), 'Left')
  right = display_name(snapshot.get('right_name'), 'Right')
  score = snapshot.get('score') or [0, 0]
  lines = [
      'Score: %s %s, %s %s. Clock %s. Ball speed %s m/s.' % (
          left, int(score[0]), right, int(score[1]),
          snapshot.get('clock') or '00:00',
          snapshot.get('speed') if snapshot.get('speed') is not None else 0),
  ]
  ball = snapshot.get('ball')
  if ball:
    lines.append('Ball position, meters, positive x toward the right end: x %s, y %s.' % (
        ball[0], ball[1]))
  lines.append(
      'Player record, one row each. Counts use the full touch log. '
      'passes is short_pass + long_pass + high_pass. '
      'x is meters along the pitch, positive toward the right end. '
      'y is meters across it. The left team attacks toward positive x. '
      'Speed is meters per second. dist is meters from the ball.')
  lines.append(
      'side team index name shirt role x y speed tired ball dist touches '
      'control trap short_pass long_pass high_pass passes header shot '
      'deflect catch last')
  for player in player_record(snapshot.get('roster'), snapshot.get('log'), ball):
    if not player.get('active', True):
      continue
    side = left if player['team'] == 0 else right
    holding = 'yes' if player.get('ball') else 'no'
    distance = '-' if player.get('dist') is None else player['dist']
    name = str(player['name']).replace(' ', '_') or '-'
    last = (player.get('last_action') or '-').replace(' ', '_')
    if player.get('last_clock'):
      last = '%s_%s' % (player['last_clock'], last)
    lines.append(
        '%s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s' % (
            side, player['team'], player['player'], name, player['shirt'],
            player['role'], player['x'], player['y'], player['speed'], player['tired'],
            holding, distance, player['touches'], player['control'], player['trap'],
            player['short_pass'], player['long_pass'], player['high_pass'],
            player['passes'], player['header'], player['shot'], player['deflect'],
            player['catch'], last))
  log = list(snapshot.get('log') or [])
  lines.append(
      'Recent touches, oldest first in this list. The counts above already '
      'include every earlier touch. A missing event is not in this log.')
  if not log:
    lines.append('No touches yet.')
  else:
    shown = log[-40:]
    if len(log) > len(shown):
      lines.append('Earlier touches omitted: %s.' % (len(log) - len(shown)))
    for row in shown:
      lines.append(_touch_line(row, left, right))
  future = snapshot.get('future', None)
  if future is not None:
    lines.append(
        'Saved match, one row per player. These counts use the whole save, '
        'including events after the clock above. goals is goals by that '
        'player. own_goals is separate. completed is a pass whose next touch '
        'is a teammate.')
    lines.append('side name shirt goals own_goals completed passes shots')
    for player in player_record(snapshot.get('roster'), future, ball):
      if not player.get('active', True):
        continue
      side = left if player['team'] == 0 else right
      name = str(player['name']).replace(' ', '_') or '-'
      lines.append('%s %s %s %s %s %s %s %s' % (
          side, name, player['shirt'], player['goal'], player['own_goal'],
          player['completed_passes'], player['passes'], player['shot']))
  return '\n'.join(lines)


def _system(snapshot):
  left = display_name(snapshot.get('left_name'), 'Left')
  right = display_name(snapshot.get('right_name'), 'Right')
  return (
      'You answer questions about this simulated football match. '
      'Use only the facts below. The player record counts every touch in the '
      'log: control, trap, short pass, long pass, high pass, header, shot, '
      'deflect, and catch. passes adds the three pass columns. '
      + ('The saved-match lines are the whole match, including events later '
         'than the clock. goals is that player\'s goals. An own goal is not '
         'one of them. completed is a pass whose next touch is a teammate. '
         if (snapshot or {}).get('future', None) is not None else
         'The log does not record a goal, a foul, a reception, or a reason. ')
      + 'The score is the '
      'goal count. If a fact is not listed, say it is not in the log. Do not '
      'invent a touch, a goal, a player, or a cause. '
      'You cannot move a player or change a formation. '
      'Reply in one or two short sentences, like "ARS 9 shot." '
      'When you mention a player, give the team, the shirt number, and the touch. '
      'Do not say that a player was boxed. '
      'Left is %s. Right is %s.\n\n%s' % (
          left, right, snapshot_text(snapshot)))


def _field_in(fragment):
  best = None
  for field, pattern in SEARCH_FIELDS.items():
    match = re.search(r'\b(?:%s)\b' % pattern, fragment)
    if not match:
      continue
    rank = (match.start(), -(match.end() - match.start()))
    if best is None or rank < best[0]:
      best = (rank, field)
  if best is None:
    return None
  return best[1]


def _overlaps(span, spans):
  return any(span[0] < end and start < span[1] for start, end in spans)


def _search_clauses(text):
  """Comparisons and shirt parity read from a highlight question."""
  clauses = []
  spans = []
  specials = (
      (r'faster than\s+(\d+)', 'speed', '>'),
      (r'slower than\s+(\d+)', 'speed', '<'),
  )
  comparisons = (
      (r'(\d+)\s+or more', '>='),
      (r'(\d+)\s+or fewer', '<='),
      (r'(\d+)\s+or less', '<='),
      (r'at least\s+(\d+)', '>='),
      (r'no more than\s+(\d+)', '<='),
      (r'at most\s+(\d+)', '<='),
      (r'more than\s+(\d+)', '>'),
      (r'(?:fewer|less) than\s+(\d+)', '<'),
      (r'(?:over|above)\s+(\d+)', '>'),
      (r'(?:under|below)\s+(\d+)', '<'),
      (r'exactly\s+(\d+)', '=='),
      (r'(\d+)\s*\+', '>='),
  )
  for pattern, field, op in specials:
    for match in re.finditer(pattern, text):
      if _overlaps(match.span(), spans):
        continue
      clauses.append({'field': field, 'op': op, 'value': int(match.group(1))})
      spans.append(match.span())
  for pattern, op in comparisons:
    for match in re.finditer(pattern, text):
      if _overlaps(match.span(), spans):
        continue
      after = text[match.end():match.end() + 28]
      before = text[max(0, match.start() - 28):match.start()]
      field = _field_in(after) or _field_in(before)
      if not field:
        continue
      clauses.append({'field': field, 'op': op, 'value': int(match.group(1))})
      spans.append(match.span())
  if re.search(r'\bodd\b', text) and re.search(r'\b(?:shirts?|numbers?|numbered)\b', text):
    clauses.append({'field': 'shirt', 'op': 'odd'})
  elif re.search(r'\beven\b', text) and re.search(r'\b(?:shirts?|numbers?|numbered)\b', text):
    clauses.append({'field': 'shirt', 'op': 'even'})
  return clauses, spans


def _record_rank(rank):
  if not (isinstance(rank, dict) and rank.get('how') in ('most', 'fewest')
          and rank.get('field') in RECORD_COLUMNS):
    return False
  try:
    count = int(rank.get('n') or 1)
  except (TypeError, ValueError):
    return False
  return 1 <= count <= 22


def _spoken_touches(text):
  """Turn 'long passed' and 'dribbled' into the touch names in the record."""
  swaps = (
      (r'\blong pass(?:ed|es|ing|ers|er)\b', 'long pass'),
      (r'\bhigh pass(?:ed|es|ing|ers|er)\b', 'high pass'),
      (r'\bshort pass(?:ed|es|ing|ers|er)\b', 'short pass'),
      (r'\bpass(?:ed|es|ing|ers|er)\b', 'pass'),
      (r'\bdribbl(?:ed|es|ing|ers|er)\b', 'dribble'),
      (r'\btrapp(?:ed|ing)\b', 'trap'),
      (r'\b(?:headed|heading|headers)\b', 'header'),
      (r'\b(?:shooting|shots)\b', 'shot'),
      (r'\bdeflect(?:ed|s|ing|ion|ions)\b', 'deflect'),
      (r'\b(?:caught|catches|catching)\b', 'catch'),
      (r'\bcontroll(?:ed|ing)\b', 'control'),
  )
  for pattern, replacement in swaps:
    text = re.sub(pattern, replacement, text)
  return text


def _mentioned_counts(text):
  """Touch columns named in the question, longest phrase first."""
  counts = (
      'completed_passes', 'own_goal', 'goal', 'short_pass', 'long_pass',
      'high_pass', 'header', 'shot', 'trap', 'control', 'deflect', 'catch',
      'passes', 'touches',
  )
  found = []
  occupied = []
  candidates = []
  for field in counts:
    pattern = SEARCH_FIELDS[field]
    for match in re.finditer(r'\b(?:%s)\b' % pattern, text):
      span = match.span()
      candidates.append((span[0], span[0] - span[1], field, span))
  for _, _, field, span in sorted(candidates):
    if _overlaps(span, occupied):
      continue
    if field not in found:
      found.append(field)
    occupied.append(span)
  return found


def _team_in_question(text, snapshot):
  """The side named in the question, from the scoreboard name or the club."""
  found = []
  for raw, side in (
      ((snapshot or {}).get('left_name') or 'FRQ', 'left'),
      ((snapshot or {}).get('right_name') or 'RBA', 'right'),
  ):
    label = display_name(raw, side).upper()
    for phrase in CLUB_NAMES.get(label, (label.lower(),)):
      found.append((phrase, side))
  found.sort(key=lambda item: len(item[0]), reverse=True)
  for phrase, side in found:
    if re.search(r'\b%s\b' % re.escape(phrase), text):
      return side
  return None


def _wants_everyone(text):
  return re.search(
      r'\b(?:everyone|everybody|both teams|all players|every player|'
      r'all the players|all of the players|all of them)\b',
      text)


def _rank_clause(text):
  """most dribbles, fewest shots, and the same shape for every count."""
  match = re.search(r'\b(most|fewest|least|highest|lowest)\b', text)
  if not match:
    return None
  how = 'fewest' if match.group(1) in ('fewest', 'least', 'lowest') else 'most'
  before = text[max(0, match.start() - 48):match.start()]
  after = text[match.end():match.end() + 48]
  field = _field_in(' ' + after + ' ') or _field_in(' ' + before + ' ')
  if field == 'passes' and re.search(r'\bcomplet(?:e|es|ed|ing)\b', text):
    field = 'completed_passes'
  if field == 'goal' and re.search(r'\bown goals?\b', before + after):
    field = 'own_goal'
  if field not in RECORD_COLUMNS:
    return None
  return {'how': how, 'field': field}


def _clock_seconds(clock):
  match = re.match(r'^(\d+):(\d{2})$', str(clock or '').strip())
  if not match:
    return None
  seconds = int(match.group(2))
  if seconds >= 60:
    return None
  return int(match.group(1)) * 60 + seconds


def _deadline_match(text):
  return re.search(
      r'\b(?:by|before|until|through|till|til)\s+(?:the\s+)?(\d{1,3})\s+(\d{2})\b',
      text)


def _clock_deadline(text):
  """Match-clock seconds for 'by 45:30'. None when the sentence has no cutoff."""
  match = _deadline_match(text)
  if not match:
    return None
  seconds = int(match.group(2))
  if seconds >= 60:
    return None
  return int(match.group(1)) * 60 + seconds


def _wants_future(text):
  """The sentence asks about the saved match, not only what has happened."""
  if _clock_deadline(text) is not None:
    return True
  return bool(re.search(
      r'\b(?:will|going to|gonna|shall)\b'
      r'|\b(?:by the end|at full time|full time|full match|whole match|this match)\b',
      text))


def _top_n(text):
  """How many players a ranking keeps. None when the sentence does not say."""
  reserved = []
  deadline = _deadline_match(text)
  if deadline:
    reserved.append(deadline.span())
  patterns = (
      r'\b(?:the|top|first|best|which)\s+(\d{1,2})\b',
      r'\b(\d{1,2})\s+(?:players?|of them|cbs?|center backs?|centre backs?|'
      r'goalkeepers?|keepers?|goalies?|defenders?|midfielders?|forwards?|'
      r'strikers?)\b',
  )
  for pattern in patterns:
    for match in re.finditer(pattern, text):
      if _overlaps(match.span(), reserved):
        continue
      count = int(match.group(1))
      if 1 <= count <= 22:
        return count
  return None


def _reserved_number_spans(text):
  """Digits that are a cutoff or a count, so they are not a shirt number."""
  spans = []
  deadline = _deadline_match(text)
  if deadline:
    spans.append(deadline.span(1))
    spans.append(deadline.span(2))
  for pattern in (
      r'\b(?:the|top|first|best|which)\s+(\d{1,2})\b',
      r'\b(\d{1,2})\s+(?:players?|of them|cbs?|center backs?|centre backs?|'
      r'goalkeepers?|keepers?|goalies?|defenders?|midfielders?|forwards?|'
      r'strikers?)\b',
  ):
    for match in re.finditer(pattern, text):
      spans.append(match.span(1))
  return spans


def _note_count(spec, text):
  """Keep the top few when the sentence says how many, present or future."""
  count = _top_n(text)
  if count and isinstance(spec.get('rank'), dict):
    spec['rank'] = dict(spec['rank'])
    spec['rank']['n'] = count
  return spec


def _note_future(spec, text):
  if not _wants_future(text):
    return spec
  spec['future'] = True
  until = _clock_deadline(text)
  if until is not None:
    spec['until'] = until
  return spec


def _events_until(log, until):
  if until is None:
    return list(log or [])
  kept = []
  for row in log or []:
    seen = _clock_seconds(row.get('clock'))
    if seen is not None and seen <= until:
      kept.append(row)
  return kept


def _roster_for(snapshot, spec):
  """Player records for this search. None when a future search has no save."""
  ball = (snapshot or {}).get('ball')
  if spec.get('future'):
    if (snapshot or {}).get('future', None) is None:
      return None
    log = _events_until((snapshot or {}).get('future'), spec.get('until'))
  else:
    log = (snapshot or {}).get('log')
  return player_record((snapshot or {}).get('roster'), log, ball)


_COUNT_WORDS = {
    'goal': 'goal',
    'own_goal': 'own goal',
    'completed_passes': 'completed pass',
    'passes': 'pass',
    'short_pass': 'short pass',
    'long_pass': 'long pass',
    'high_pass': 'high pass',
    'shot': 'shot',
    'header': 'header',
    'control': 'dribble',
    'trap': 'trap',
    'deflect': 'deflection',
    'catch': 'catch',
    'touches': 'touch',
}


def _future_reply(verb, players, spec, left, right):
  if not players:
    return 'No player in the match matches that.'
  rank = spec.get('rank') if isinstance(spec.get('rank'), dict) else None
  field = rank.get('field') if rank else None
  if field is None:
    where = [clause for clause in (spec.get('where') or []) if isinstance(clause, dict)]
    if len(where) == 1 and where[0].get('field') in _COUNT_WORDS:
      field = where[0].get('field')
  until = spec.get('until')
  when = ''
  if isinstance(until, int):
    when = ' by %d:%02d' % (until // 60, until % 60)
  parts = []
  for player in players:
    side = left if player['team'] == 0 else right
    bit = '%s %s %s' % (side, player['name'], player['shirt'])
    if field in _COUNT_WORDS:
      count = int(player.get(field) or 0)
      word = _COUNT_WORDS[field]
      if count != 1:
        word = {
            'pass': 'passes',
            'completed pass': 'completed passes',
            'short pass': 'short passes',
            'long pass': 'long passes',
            'high pass': 'high passes',
        }.get(word, word if word.endswith('s') else word + 's')
      bit = '%s, %s %s' % (bit, count, word)
    parts.append(bit)
  if len(parts) == 1:
    body = parts[0]
  elif len(parts) == 2:
    body = '%s and %s' % (parts[0], parts[1])
  else:
    body = '%s, and %s' % (', '.join(parts[:-1]), parts[-1])
  if verb:
    return '%s %s%s.' % (verb, body, when)
  if when:
    return 'By %d:%02d: %s.' % (until // 60, until % 60, body)
  return '%s.' % body


def _moment_rows(snapshot):
  """The whole saved list when the match has one, otherwise the present log."""
  future = (snapshot or {}).get('future')
  if isinstance(future, list):
    return future
  return (snapshot or {}).get('log') or []


def _clock_label(seconds):
  seconds = max(0, int(seconds))
  return '%d:%02d' % (seconds // 60, seconds % 60)


def goal_segments(rows):
  """One clip per goal, from 60 seconds before it through the goal.

  This is the chat command, not an automatic ranking of moments.
  """
  indexed = []
  for index, row in enumerate(rows or []):
    if not isinstance(row, dict):
      continue
    clock = _clock_seconds(row.get('clock'))
    if clock is None:
      continue
    action = str(row.get('action') or '').strip().upper()
    indexed.append((clock, index, action, str(row.get('clock') or '')))
  indexed.sort(key=lambda item: (item[0], item[1]))
  goals = 0
  segments = []
  for clock, _index, action, label in indexed:
    if action not in ('GOAL', 'OWN GOAL'):
      continue
    goals += 1
    start = max(0, int(clock) - 60)
    segments.append({
        'start': start,
        'end': int(clock),
        'start_clock': _clock_label(start),
        'end_clock': label or _clock_label(clock),
    })
  return goals, segments


def key_moments_from_question(question, snapshot=None):
  """Highlight key moments, or None when the sentence is not that request.

  The pair is the reply and the clips. An empty list clears the clips.
  """
  text = ' ' + re.sub(r'[^a-z0-9]+', ' ', str(question or '').lower()) + ' '
  if not re.search(r'\bkey moments?\b', text):
    return None
  clearing = re.search(r'\b(?:unhighlight|un highlight|clear|remove|hide)\b', text)
  asking = re.search(r'\b(?:highlight|mark|show|find(?:ing)?)\b', text)
  if clearing:
    return 'Key moments cleared.', []
  if not asking:
    return None
  goals, segments = goal_segments(_moment_rows(snapshot))
  if goals == 0 or not segments:
    return 'No goal on this timeline.', []
  if len(segments) == 1:
    row = segments[0]
    return 'Key moment, %s to %s.' % (row['start_clock'], row['end_clock']), segments
  return '%d key moments.' % len(segments), segments


def highlight_from_question(question, snapshot=None):
  """The standardized box request, read from the question itself.

  A question that does not ask to mark anyone returns None, and the boxes
  stay as they are. clear removes them. Anything else is a filter.
  """
  text = ' ' + re.sub(r'[^a-z0-9#+]+', ' ', str(question or '').lower()) + ' '
  for word, number in _NUMBER_WORDS.items():
    text = re.sub(r'\b%s\b' % word, str(number), text)
  if re.search(r'\bunhighlight\b|\bun highlight\b|\bunbox\b', text):
    return {'clear': True}
  if (re.search(r'\b(clear|remove|hide|stop)\b', text) and
      re.search(r'\b(boxes|box|highlights|highlighting|highlight)\b', text)):
    return {'clear': True}
  text = _spoken_touches(text)
  spec = {}
  if _REFEREE.search(text):
    spec['official'] = 'referee'
  side_in_role = False
  for pattern, role, sided in _ROLE_PATTERNS:
    if re.search(pattern, text):
      spec['role'] = role
      side_in_role = sided
      break
  if not side_in_role:
    if re.search(r'\bleft\b', text):
      spec['team'] = 'left'
    elif re.search(r'\bright\b', text):
      spec['team'] = 'right'
  if 'team' not in spec:
    side = _team_in_question(text, snapshot)
    if side:
      spec['team'] = side
  _apply_role_group(text, spec)
  if re.search(r'\bown half\b|\bdefensive half\b', text):
    spec['zone'] = 'own_half'
  elif re.search(r'\battacking half\b|\bfinal third\b', text):
    spec['zone'] = 'attacking_half'
  elif re.search(r'\bwide\b|\btouchline\b|\bflank\b', text):
    spec['zone'] = 'wide'
  elif re.search(r'\bnear the ball\b|\bclose to the ball\b', text):
    spec['zone'] = 'near_ball'
  elif 'role' not in spec and re.search(r'\b(?:centre|center) of the pitch\b', text):
    spec['zone'] = 'center'
  if re.search(r'\b(?:fastest|quickest)\b', text):
    spec['stat'] = 'fastest'
  elif re.search(r'\bslowest\b', text):
    spec['stat'] = 'slowest'
  elif re.search(r'\bmost touches\b', text):
    spec['stat'] = 'most_touches'
  elif re.search(r'\b(?:fewest|least) touches\b', text):
    spec['stat'] = 'fewest_touches'
  elif re.search(r'\b(?:has the ball|with the ball|on the ball)\b', text):
    spec['stat'] = 'has_ball'
  elif re.search(r'\bmost tired\b', text):
    spec['stat'] = 'most_tired'
  if 'stat' not in spec:
    rank = _rank_clause(text)
    if rank:
      spec['rank'] = rank
  clauses, spans = _search_clauses(text)
  if clauses:
    spec['where'] = clauses
  shirt = re.search(r'\b(?:shirt|number)\s*(\d{1,2})\b|#(\d{1,2})\b', text)
  if shirt and not _overlaps(shirt.span(1) if shirt.group(1) else shirt.span(2), spans):
    spec['shirt'] = int(next(group for group in shirt.groups() if group))
  named = re.search(r'\bnamed\s+([a-z]+)\b', text)
  if named:
    spec['name'] = named.group(1)
  if not spec.get('where') and 'rank' not in spec and 'stat' not in spec:
    mentioned = _mentioned_counts(text)
    if mentioned:
      spec['where'] = [
          {'field': field, 'op': '>=', 'value': 1} for field in mentioned]
  if not _narrowed(spec) and _wants_everyone(text):
    spec['everyone'] = True
  _note_future(spec, text)
  _note_count(spec, text)
  asked = re.search(r'\b(?:highlight|box|mark|select)\b', text)
  if not asked and not (re.search(r'\bshow\b', text) and spec):
    return None
  return spec


def _visible(content):
  lines = []
  for line in str(content or '').splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith('HIGHLIGHT') or stripped[:1] in '{[':
      continue
    lines.append(stripped)
  return ' '.join(lines).strip()


def _apply_role_group(text, spec):
  """A word that names more than one role. Fullbacks are the two wide defenders."""
  if _FULLBACKS.search(text):
    spec['roles'] = ['LB', 'RB']
    spec.pop('role', None)
  elif _DEFENDERS.search(text):
    spec['roles'] = ['CB', 'LB', 'RB']
    spec.pop('role', None)
  return spec


def _narrowed(spec):
  if (spec.get('where') or spec.get('everyone') or spec.get('official') or
      spec.get('roles') or _record_rank(spec.get('rank'))):
    return True
  return any(spec.get(key) not in (None, '', False)
             for key in ('team', 'role', 'zone', 'stat', 'shirt', 'name'))


def extract_highlight(content):
  """Split a reply into the sentence and a highlight filter, if one was asked."""
  text = str(content or '').strip()
  marker = text.rfind('HIGHLIGHT')
  blob = text[marker + len('HIGHLIGHT'):] if marker >= 0 else text
  start = blob.find('{')
  end = blob.rfind('}')
  if start < 0 or end <= start:
    return text, None
  try:
    raw = json.loads(blob[start:end + 1])
  except json.JSONDecodeError:
    return text, None
  if not isinstance(raw, dict):
    return text, None
  spec = {}
  for key in ('clear', 'team', 'role', 'zone', 'stat', 'shirt', 'name'):
    value = raw.get(key)
    if isinstance(value, bool) or (isinstance(value, (int, float)) and not isinstance(value, bool)):
      if value is False or value == '':
        continue
      spec[key] = value
    elif isinstance(value, str) and value.strip():
      spec[key] = value.strip()
  if not spec:
    return text, None
  if marker >= 0:
    spoken = text[:marker].strip()
  elif text[:start].strip():
    spoken = text[:start].strip()
  else:
    spoken = ''
  return spoken, spec


def _marks(players):
  marks = []
  seen = set()
  for player in players:
    key = (int(player['team']), int(player['player']))
    if key in seen:
      continue
    seen.add(key)
    marks.append({'team': key[0], 'player': key[1]})
  return marks


def _apply_highlight(spec, snapshot):
  left = display_name((snapshot or {}).get('left_name'), 'Left')
  right = display_name((snapshot or {}).get('right_name'), 'Right')
  if spec.get('clear'):
    return 'Boxes cleared.', []
  referee = spec.get('official') == 'referee'
  if not _narrowed(spec):
    return 'Say which players to box.', None
  roster = _roster_for(snapshot, spec)
  if roster is None:
    return 'This match has no saved touch list.', None
  ball = (snapshot or {}).get('ball')
  selected = select_players(roster, spec, ball)
  if not selected and not referee:
    return 'No player in the match matches that.', []
  marks = _marks(selected)
  if referee:
    marks.append({'team': -1, 'player': 0})
  if referee and not selected:
    return 'Boxed the referee.', marks
  rank = spec.get('rank') if isinstance(spec.get('rank'), dict) else None
  try:
    several = rank and int(rank.get('n') or 1) > 1
  except (TypeError, ValueError):
    several = False
  if (spec.get('future') or several) and not referee:
    return _future_reply('Boxed', selected, spec, left, right), marks
  text = describe_highlight(selected, spec, left, right)
  if referee:
    text = text[:-1] + ' and the referee.'
  return text, marks


_NUMBER_WORDS = {
    'two': 2,
    'three': 3,
    'four': 4,
    'five': 5,
    'six': 6,
    'seven': 7,
    'eight': 8,
    'nine': 9,
    'ten': 10,
    'eleven': 11,
}

_EYES = re.compile(
    r'\b(?:first person|1st person|fpv|pov|point of view|perspective|viewpoint)\b'
    r'|\b(?:through (?:his|her|their) eyes|eyes of|from the eyes)\b'
    r'|\bs eyes\b|\bs angle\b|\bs view\b|\bview of\b')
_FOLLOW = re.compile(
    r'\b(?:follow|following|track|tracking|chase|chasing|tail|tailing)\b'
    r'|\b(?:stick|stay) (?:on|with)\b'
    r'|\bcamera on\b'
    r'|\blong lens on\b'
    r'|\baction (?:camera|cam|view) on\b'
    r'|\b(?:put|set|switch|change) (?:the )?(?:camera|view|angle) (?:on|to)\b')
_BROADCAST = re.compile(
    r'\bbroadcast\b|\btv camera\b|\btelevision camera\b'
    r'|\bwide (?:camera|shot|angle)\b|\bdefault camera\b')
_FREE = re.compile(r'\bfree (?:camera|cam|look|view)\b')
_ACTION = re.compile(
    r'\baction (?:camera|cam|view)\b'
    r'|\bfollow(?:ing)? (?:the )?(?:ball|play)\b'
    r'|\bfollow(?:ing)? the action\b')
_QUESTION = re.compile(
    r'^(?:who|what|why|when|where|how|did|does|is|are|was|were|which|whose)\b')


def _camera_text(question):
  """Lower case, without polite filler, and with shirt words as digits."""
  text = str(question or '').lower().replace("'", '')
  text = re.sub(r'[^a-z0-9#+]+', ' ', text)
  text = re.sub(
      r'\b(?:please|can you|could you|would you|will you|i want to|i wanna|'
      r'id like to|i would like to|let me|lets|lemme)\b',
      ' ', text)
  for word, number in _NUMBER_WORDS.items():
    text = re.sub(r'\b%ss\b' % word, '%ss' % number, text)
    text = re.sub(r'\b%s\b' % word, str(number), text)
  text = re.sub(r'\b(?:shirt|number|num|no)\s+one\b', 'number 1', text)
  text = re.sub(r'\bones\b', '1s', text)
  return ' ' + re.sub(r'\s+', ' ', text).strip() + ' '


def _camera_names(snapshot):
  names = []
  for row in (snapshot or {}).get('roster') or []:
    name = str(row.get('name') or '').strip().lower()
    if len(name) >= 3 and name not in names:
      names.append(name)
  names.sort(key=len, reverse=True)
  return names


def _camera_spec(text, snapshot):
  """The player a camera sentence points at, in the highlight filter shape."""
  text = _spoken_touches(text)
  spec = {}
  side_in_role = False
  for pattern, role, sided in _ROLE_PATTERNS:
    if re.search(pattern, text):
      spec['role'] = role
      side_in_role = sided
      break
  if not side_in_role:
    if re.search(r'\bleft\b', text):
      spec['team'] = 'left'
    elif re.search(r'\bright\b', text):
      spec['team'] = 'right'
  if 'team' not in spec:
    side = _team_in_question(text, snapshot)
    if side:
      spec['team'] = side
  _apply_role_group(text, spec)
  if re.search(r'\bown half\b|\bdefensive half\b', text):
    spec['zone'] = 'own_half'
  elif re.search(r'\battacking half\b|\bfinal third\b', text):
    spec['zone'] = 'attacking_half'
  elif re.search(r'\bwide\b|\btouchline\b|\bflank\b', text) and 'wide camera' not in text:
    spec['zone'] = 'wide'
  elif re.search(r'\bnear the ball\b|\bclose to the ball\b', text):
    spec['zone'] = 'near_ball'
  if re.search(r'\b(?:fastest|quickest)\b', text):
    spec['stat'] = 'fastest'
  elif re.search(r'\bslowest\b', text):
    spec['stat'] = 'slowest'
  elif re.search(r'\bmost touches\b', text):
    spec['stat'] = 'most_touches'
  elif re.search(r'\b(?:fewest|least) touches\b', text):
    spec['stat'] = 'fewest_touches'
  elif re.search(r'\b(?:has the ball|with the ball|on the ball|ball carrier)\b', text):
    spec['stat'] = 'has_ball'
  elif re.search(r'\bmost tired\b', text):
    spec['stat'] = 'most_tired'
  if 'stat' not in spec:
    rank = _rank_clause(text)
    if rank:
      spec['rank'] = rank
  clauses, spans = _search_clauses(text)
  if clauses:
    spec['where'] = clauses
  reserved = spans + _reserved_number_spans(text)
  shirt = None
  for pattern in (
      r'#(\d{1,2})\b',
      r'\b(?:shirt|number|num|no)\s*(\d{1,2})\b',
      r'\b(\d{1,2})s\b',
      r'\b(\d{1,2})\b',
  ):
    found = None
    for match in re.finditer(pattern, text):
      if _overlaps(match.span(1), reserved):
        continue
      found = match
      break
    if found:
      shirt = int(found.group(1))
      break
  if shirt is not None and 0 < shirt <= 99:
    spec['shirt'] = shirt
  if not spec.get('where') and 'rank' not in spec and 'stat' not in spec:
    mentioned = _mentioned_counts(text)
    if mentioned:
      spec['where'] = [
          {'field': field, 'op': '>=', 'value': 1} for field in mentioned]
  for name in _camera_names(snapshot):
    if re.search(r'\b%s(?:s)?\b' % re.escape(name), text):
      spec['name'] = name
      break
  return _note_count(_note_future(spec, text), text)


def _camera_label(player, snapshot):
  left = display_name((snapshot or {}).get('left_name'), 'Left')
  right = display_name((snapshot or {}).get('right_name'), 'Right')
  side = left if player['team'] == 0 else right
  return '%s %s %s' % (side, player['name'], player['shirt'])


def _fixed_camera(mode):
  if mode == 'broadcast':
    return 'Broadcast.', {'team': -1, 'player': 0, 'lens': 0}
  if mode == 'action':
    return 'Action camera.', {'team': -1, 'player': 0, 'lens': 2}
  return 'Free camera.', {'team': -1, 'player': 0, 'lens': 3}


def camera_from_question(question, snapshot=None):
  """A camera command, or None when the sentence is not one.

  The pair is the reply and the view. The view is None when the sentence
  names more than one player. Perspective is lens 0, at that player's eyes.
  Follow is lens 1, the long lens on that player. Broadcast, the action
  camera, and the free camera do not name a player.
  """
  text = _camera_text(question)
  if _QUESTION.match(text.strip()):
    return None
  if re.search(r'\b(?:highlight|unhighlight|unbox|box|mark|select)\b', text):
    return None
  spec = _camera_spec(text, snapshot)
  has_player = _narrowed(spec)
  eyes = _EYES.search(text) or (
      re.search(r'\beyes\b', text) and not re.search(r'\beyes on\b', text))
  follow = _FOLLOW.search(text)
  if eyes:
    mode = 'eyes'
  elif has_player and follow:
    mode = 'follow'
  elif (re.search(r'\bshow\b', text) and not follow and
        (spec.get('shirt') or spec.get('name')) and not spec.get('role') and
        not spec.get('zone') and not spec.get('stat') and 'rank' not in spec and
        not spec.get('where')):
    mode = 'eyes'
  elif _BROADCAST.search(text) and not has_player:
    mode = 'broadcast'
  elif _FREE.search(text) and not has_player:
    mode = 'free'
  elif (_ACTION.search(text) or (follow and re.search(r'\b(?:ball|play)\b', text))) and not has_player:
    mode = 'action'
  elif follow:
    mode = 'follow'
  elif re.search(r'\b(?:switch|change) (?:the )?(?:camera|view|angle)\b', text):
    return 'Say which camera.', None
  else:
    return None
  if mode in ('broadcast', 'action', 'free'):
    return _fixed_camera(mode)
  if not has_player:
    if mode == 'follow' and re.search(r'\b(?:ball|play)\b', text):
      return _fixed_camera('action')
    return 'Say which player.', None
  roster = _roster_for(snapshot, spec)
  if roster is None:
    return 'This match has no saved touch list.', None
  rows = select_players(roster, spec, (snapshot or {}).get('ball'))
  if not rows:
    return 'No player in the match matches that.', None
  if len(rows) > 1:
    if len(rows) == 2:
      return '%s and %s. Say which one.' % (
          _camera_label(rows[0], snapshot),
          _camera_label(rows[1], snapshot)), None
    return 'Say which player.', None
  player = rows[0]
  label = _camera_label(player, snapshot)
  lens = 0 if mode == 'eyes' else 1
  choice = {
      'team': int(player['team']),
      'player': int(player['player']),
      'lens': lens,
  }
  if lens == 0:
    return 'First person, %s.' % label, choice
  return 'Following %s.' % label, choice


def _stored_hidden(snapshot):
  raw = (snapshot or {}).get('hidden') or {}
  players = []
  seen = set()
  for row in raw.get('players') or []:
    try:
      key = (int(row['team']), int(row['player']))
    except (KeyError, TypeError, ValueError):
      continue
    if key in seen:
      continue
    seen.add(key)
    players.append({'team': key[0], 'player': key[1]})
  return players, bool(raw.get('ball'))


def _visibility_targets(text, snapshot):
  """Players, the referee, and the ball a hide or show sentence names."""
  spec = _camera_spec(text, snapshot)
  roles = []
  if re.search(r'\bdefenders?\b', text):
    roles.extend(['CB', 'LB', 'RB'])
  role = spec.get('role')
  if role and role not in roles:
    roles.append(role)
  if roles and (len(roles) > 1 or re.search(r'\bdefenders?\b', text)):
    spec['roles'] = roles
    spec.pop('role', None)
  ball_named = bool(re.search(r'\bballs?\b', text)) and not re.search(
      r'\b(?:with|on|has|have) the ball\b|\bball carrier\b', text)
  referee = bool(_REFEREE.search(text))
  everything = bool(re.search(r'\beverything\b', text))
  narrowed = bool(roles) or _narrowed(spec)
  everyone = everything or (
      not narrowed and (
          bool(_wants_everyone(text)) or bool(re.search(r'\ball\b', text))))
  return spec, ball_named, referee, everyone, everything


def _visibility_sentence(mode, players, ball, referee, everyone, left, right):
  verb = 'Hid' if mode == 'hide' else 'Showing'
  bits = []
  if everyone:
    bits.append('every player')
  elif len(players) > 2:
    bits.append('%s players' % len(players))
  else:
    for player in players:
      side = left if player['team'] == 0 else right
      bits.append('%s %s %s' % (side, player['name'], player['shirt']))
  if referee:
    bits.append('the referee')
  if ball:
    bits.append('the ball')
  if len(bits) == 1:
    return '%s %s.' % (verb, bits[0])
  if len(bits) > 1:
    return '%s %s and %s.' % (verb, ', '.join(bits[:-1]), bits[-1])
  return None


def visibility_from_question(question, snapshot=None):
  """A hide or show command, or None when the sentence is not one.

  The pair is the reply and the full hidden set. The set is None when the
  sentence names nobody, and the picture stays as it is. show me stays a
  camera or a highlight. Hide and show add to or remove from the set.
  """
  text = _camera_text(question)
  if _QUESTION.match(text.strip()):
    return None
  hide_at = re.search(r'\b(?:hide|unshow)\b', text)
  show_at = re.search(r'\b(?:show|unhide|reveal)\b', text)
  if hide_at is None and show_at is None:
    return None
  if hide_at is None and re.search(r'\bshow me\b', text):
    return None
  if hide_at is None and (
      _EYES.search(text) or _FOLLOW.search(text) or _BROADCAST.search(text) or
      _FREE.search(text) or _ACTION.search(text)):
    return None
  if hide_at and re.search(
      r'\b(?:boxes|box|highlights|highlighting|highlight)\b', text):
    return None
  mode = 'hide'
  if show_at and (hide_at is None or show_at.start() < hide_at.start()):
    mode = 'show'
  spec, ball_named, referee, everyone, everything = _visibility_targets(
      text, snapshot)
  roster = _roster_for(snapshot, spec)
  if roster is None:
    return 'This match has no saved touch list.', None
  selected = []
  if not everyone:
    selected = select_players(roster, spec, (snapshot or {}).get('ball'))
  if not selected and not ball_named and not referee and not everyone:
    if _narrowed(spec) or spec.get('roles'):
      return 'No player in the match matches that.', None
    return 'Say what to %s.' % mode, None
  left = display_name((snapshot or {}).get('left_name'), 'Left')
  right = display_name((snapshot or {}).get('right_name'), 'Right')
  stored, ball_hidden = _stored_hidden(snapshot)
  keys = {(row['team'], row['player']) for row in stored}
  chosen = []
  if everyone:
    chosen = [row for row in roster if row.get('active', True)]
  else:
    chosen = selected
  chosen_keys = {(int(row['team']), int(row['player'])) for row in chosen}
  if referee:
    chosen_keys.add((-1, 0))
  if everything and mode == 'hide':
    chosen_keys = {(int(row['team']), int(row['player']))
                   for row in roster if row.get('active', True)}
    chosen_keys.add((-1, 0))
    ball_named = True
  if everything and mode == 'show':
    chosen_keys = set(keys)
    referee = True
    ball_named = True
  if mode == 'hide':
    keys.update(chosen_keys)
    if ball_named:
      ball_hidden = True
  else:
    keys.difference_update(chosen_keys)
    if ball_named:
      ball_hidden = False
    if everything:
      keys.clear()
      ball_hidden = False
  players = [{'team': team, 'player': index} for team, index in sorted(keys)]
  named = chosen if not everything else []
  sentence = _visibility_sentence(
      mode, [] if everyone or everything else named,
      ball_named, referee and not everything, everyone or everything,
      left, right)
  if everything and mode == 'show':
    sentence = 'Showing everything.'
  if everything and mode == 'hide':
    sentence = 'Hid everything.'
  return sentence, {'players': players, 'ball': ball_hidden}


def captions_from_question(question, snapshot=None):
  """Turn the head labels on or off. The chat calls them captions.

  The pair is the reply and the new state. None when the sentence is not
  about those labels, and the labels stay as they are.
  """
  text = _camera_text(question)
  if not re.search(r'\b(?:captions?|head ?labels?)\b', text):
    return None
  off = re.search(r'\b(?:off|disable|disabled|hide|stop)\b', text)
  on = re.search(r'\b(?:on|enable|enabled|show)\b', text)
  if off and (on is None or off.start() < on.start()):
    enabled = False
  elif on:
    enabled = True
  elif re.search(r'\btoggle\b', text):
    enabled = not bool((snapshot or {}).get('captions', True))
  else:
    return 'Say captions on or off.', None
  return ('Captions off.' if not enabled else 'Captions on.'), enabled


def _line_pair(a, b):
  if a > b:
    a, b = b, a
  return {
      'a': {'team': a[0], 'player': a[1]},
      'b': {'team': b[0], 'player': b[1]},
  }


def _stored_lines(snapshot):
  lines = []
  seen = set()
  for row in (snapshot or {}).get('lines') or []:
    try:
      a = (int(row['a']['team']), int(row['a']['player']))
      b = (int(row['b']['team']), int(row['b']['player']))
    except (KeyError, TypeError, ValueError):
      continue
    if a == b or a[0] not in (0, 1) or b[0] not in (0, 1):
      continue
    pair = (a, b) if a < b else (b, a)
    if pair in seen:
      continue
    seen.add(pair)
    lines.append(_line_pair(a, b))
  return lines


def _pair_lines(players):
  keys = []
  for row in players or []:
    try:
      key = (int(row['team']), int(row['player']))
    except (KeyError, TypeError, ValueError):
      continue
    if key[0] not in (0, 1) or key in keys:
      continue
    keys.append(key)
  lines = []
  for i in range(len(keys)):
    for j in range(i + 1, len(keys)):
      lines.append(_line_pair(keys[i], keys[j]))
  return lines


def _across_lines(group_a, group_b):
  """A line from each player in the first group to each player in the second."""
  lines = []
  seen = set()
  for a in group_a or []:
    for b in group_b or []:
      try:
        left = (int(a['team']), int(a['player']))
        right = (int(b['team']), int(b['player']))
      except (KeyError, TypeError, ValueError):
        continue
      if left == right or left[0] not in (0, 1) or right[0] not in (0, 1):
        continue
      pair = (left, right) if left < right else (right, left)
      if pair in seen:
        continue
      seen.add(pair)
      lines.append(_line_pair(left, right))
  return lines


def _across_sentence(group_a, group_b, left_name, right_name):
  def label(player):
    side = left_name if player['team'] == 0 else right_name
    return '%s %s %s' % (side, player['name'], player['shirt'])

  def side(players):
    if len(players) == 1:
      return label(players[0])
    if len(players) == 2:
      return '%s and %s' % (label(players[0]), label(players[1]))
    return '%s, and %s' % (
        ', '.join(label(player) for player in players[:-1]), label(players[-1]))

  return 'Connected %s to %s.' % (side(group_a), side(group_b))


def _line_players(text, snapshot):
  """The players a connect sentence names, using the same search as a box."""
  spec = _camera_spec(text, snapshot)
  roles = []
  if re.search(r'\bdefenders?\b', text):
    roles.extend(['CB', 'LB', 'RB'])
  role = spec.get('role')
  if role and role not in roles:
    roles.append(role)
  if roles and (len(roles) > 1 or re.search(r'\bdefenders?\b', text)):
    spec['roles'] = roles
    spec.pop('role', None)
  roster = _roster_for(snapshot, spec)
  if roster is None:
    return None, True
  named = []
  seen = set()
  occupied = []
  for name in _camera_names(snapshot):
    found = re.search(r'\b%s(?:s)?\b' % re.escape(name), text)
    if not found or _overlaps(found.span(), occupied):
      continue
    occupied.append(found.span())
    exact = [row for row in roster
             if row.get('active', True) and str(row.get('name') or '').lower() == name]
    rows = exact or [row for row in roster
                     if row.get('active', True) and
                     str(row.get('name') or '').lower().startswith(name)]
    for row in rows:
      key = (int(row['team']), int(row['player']))
      if key in seen:
        continue
      seen.add(key)
      named.append(row)
  if len(named) >= 2:
    return named, True
  shirts = []
  for found in re.finditer(r'#(\d{1,2})\b|\b(\d{1,2})s?\b', text):
    number = int(next(group for group in found.groups() if group))
    if 0 < number <= 99 and number not in shirts:
      shirts.append(number)
  if len(shirts) >= 2 and not spec.get('role') and not spec.get('roles'):
    rows = [row for row in roster if row.get('active', True) and row.get('shirt') in shirts]
    team = spec.get('team')
    if team == 'left':
      rows = [row for row in rows if row['team'] == 0]
    elif team == 'right':
      rows = [row for row in rows if row['team'] == 1]
    return rows, True
  narrowed = _narrowed(spec) or bool(spec.get('roles'))
  everyone = (not narrowed) and bool(_wants_everyone(text))
  if everyone:
    return [row for row in roster if row.get('active', True)], True
  if not narrowed:
    return [], False
  return select_players(roster, spec, (snapshot or {}).get('ball')), True


def _line_sentence(verb, players, everyone, left, right):
  if everyone:
    return '%s every player.' % verb
  if len(players) > 2:
    return '%s %s players.' % (verb, len(players))
  parts = []
  for player in players:
    side = left if player['team'] == 0 else right
    parts.append('%s %s %s' % (side, player['name'], player['shirt']))
  if len(parts) == 2:
    return '%s %s and %s.' % (verb, parts[0], parts[1])
  if len(parts) == 1:
    return '%s %s.' % (verb, parts[0])
  return '%s.' % verb


def lines_from_question(question, snapshot=None):
  """Draw or clear lines between players.

  The pair is the reply and the full line list. None for the list when the
  lines stay as they are. A connect adds a line between every pair in the
  named group. "Connect A to B" draws a line from each player before "to"
  to each player after it. Clear lines removes them.
  """
  text = _camera_text(question)
  if _QUESTION.match(text.strip()) or re.search(r'\bshow me\b', text):
    return None
  if re.search(r'\b(?:highlight|unhighlight|unbox|boxes|box)\b', text):
    return None
  connecting = bool(re.search(r'\b(?:connect|link|join)\b', text) or (
      re.search(r'\b(?:draw|drawing)\b', text) and
      re.search(r'\b(?:lines?|connections?)\b', text)))
  clearing = bool(re.search(
      r'\b(?:clear|remove|erase|delete|disconnect|unconnect|stop|hide)\b', text) and
      re.search(r'\b(?:lines?|connections?)\b', text))
  if re.search(r'\b(?:disconnect|unconnect)\b', text):
    clearing = True
  if not connecting and not clearing:
    return None
  if connecting and clearing:
    connect_at = re.search(r'\b(?:connect|link|join|draw|drawing)\b', text)
    clear_at = re.search(
        r'\b(?:clear|remove|erase|delete|disconnect|unconnect|stop|hide)\b', text)
    if clear_at and (connect_at is None or clear_at.start() < connect_at.start()):
      connecting = False
    else:
      clearing = False
  left = display_name((snapshot or {}).get('left_name'), 'Left')
  right = display_name((snapshot or {}).get('right_name'), 'Right')
  stored = _stored_lines(snapshot)
  if clearing and not connecting:
    players, asked = _line_players(text, snapshot)
    if players is None:
      return 'This match has no saved touch list.', None
    if not asked:
      cleared = 'Connections cleared.' if re.search(r'\bconnections?\b', text) else 'Lines cleared.'
      return cleared, []
    if not players:
      return 'No player in the match matches that.', None
    if len(players) < 2:
      return 'Say another player to disconnect.', None
    chosen = {(int(row['team']), int(row['player'])) for row in players}
    kept = []
    removed = False
    for row in stored:
      a = (int(row['a']['team']), int(row['a']['player']))
      b = (int(row['b']['team']), int(row['b']['player']))
      if a in chosen and b in chosen:
        removed = True
        continue
      kept.append(row)
    if not removed:
      return 'No line between them.', None
    everyone = (not (_narrowed(_camera_spec(text, snapshot)))) and bool(
        _wants_everyone(text))
    if not kept and not players:
      return 'Lines cleared.', []
    return _line_sentence('Disconnected', players, everyone, left, right), kept
  halves = re.split(r'\bto\b', text, maxsplit=1)
  if len(halves) == 2 and halves[0].strip() and halves[1].strip():
    group_a, asked_a = _line_players(halves[0], snapshot)
    group_b, asked_b = _line_players(halves[1], snapshot)
    if group_a is None or group_b is None:
      return 'This match has no saved touch list.', None
    if not asked_a or not asked_b:
      return 'Say who to connect.', None
    if not group_a or not group_b:
      return 'No player in the match matches that.', None
    fresh = _across_lines(group_a, group_b)
    if not fresh:
      return 'Say another player to connect.', None
    seen = {(
        (int(row['a']['team']), int(row['a']['player'])),
        (int(row['b']['team']), int(row['b']['player'])),
    ) for row in stored}
    merged = list(stored)
    for row in fresh:
      key = (
          (int(row['a']['team']), int(row['a']['player'])),
          (int(row['b']['team']), int(row['b']['player'])),
      )
      if key in seen:
        continue
      seen.add(key)
      merged.append(row)
    return _across_sentence(group_a, group_b, left, right), merged
  players, asked = _line_players(text, snapshot)
  if players is None:
    return 'This match has no saved touch list.', None
  if not asked:
    return 'Say who to connect.', None
  if not players:
    return 'No player in the match matches that.', None
  if len(players) < 2:
    return 'Say another player to connect.', None
  fresh = _pair_lines(players)
  seen = {(
      (int(row['a']['team']), int(row['a']['player'])),
      (int(row['b']['team']), int(row['b']['player'])),
  ) for row in stored}
  merged = list(stored)
  for row in fresh:
    key = (
        (int(row['a']['team']), int(row['a']['player'])),
        (int(row['b']['team']), int(row['b']['player'])),
    )
    if key in seen:
      continue
    seen.add(key)
    merged.append(row)
  spec = _camera_spec(text, snapshot)
  try:
    several = (isinstance(spec.get('rank'), dict) and
               int(spec['rank'].get('n') or 1) > 1)
  except (TypeError, ValueError):
    several = False
  if spec.get('future') or several:
    return _future_reply('Connected', players, spec, left, right), merged
  everyone = (not (_narrowed(spec) or
                   bool(re.search(r'\bdefenders?\b', text)))) and bool(
      _wants_everyone(text))
  return _line_sentence('Connected', players, everyone and len(players) > 2,
                        left, right), merged


def _future_question(question, snapshot):
  """A who or which question about the saved match, with no picture change."""
  text = _camera_text(question)
  if not _wants_future(text):
    return None
  if not (_QUESTION.match(text.strip()) or re.search(r'\bwho\b', text)):
    return None
  spec = _camera_spec(text, snapshot)
  if not spec.get('future'):
    return None
  if not (_record_rank(spec.get('rank')) or spec.get('where') or spec.get('stat')):
    return None
  roster = _roster_for(snapshot, spec)
  if roster is None:
    return 'This match has no saved touch list.'
  rows = select_players(roster, spec, (snapshot or {}).get('ball'))
  left = display_name((snapshot or {}).get('left_name'), 'Left')
  right = display_name((snapshot or {}).get('right_name'), 'Right')
  return _future_reply('', rows, spec, left, right)


def formation_from_question(question, snapshot=None):
  """The formation command, or None when the sentence is not one."""
  return formations.formation_from_question(question, snapshot)


def answer(question, snapshot, history=None, url=OLLAMA_CHAT, timeout=30):
  """Return (text, marks, camera, hidden, captions, lines).

  marks is None when the boxes stay as they are. camera is None when the
  view stays as it is. hidden is None when the hidden players and ball stay
  as they are. captions is None when the head labels stay as they are.
  lines is None when the lines between players stay as they are.
  """
  question = str(question or '').strip()
  if not question:
    raise MatchChatError('Ask about a touch, a player, or the score.')
  found = key_moments_from_question(question, snapshot)
  if found is not None:
    text, _segments = found
    return text, None, None, None, None, None
  formed = formations.formation_from_question(question, snapshot)
  if formed is not None:
    return formed['text'], None, None, None, None, None
  found = captions_from_question(question, snapshot)
  if found is not None:
    text, captions = found
    return text, None, None, None, captions, None
  found = lines_from_question(question, snapshot)
  if found is not None:
    text, lines = found
    return text, None, None, None, None, lines
  found = visibility_from_question(question, snapshot)
  if found is not None:
    text, hidden = found
    return text, None, None, hidden, None, None
  found = camera_from_question(question, snapshot)
  if found is not None:
    text, camera = found
    return text, None, camera, None, None, None
  asked = highlight_from_question(question, snapshot)
  if asked is not None:
    text, marks = _apply_highlight(asked, snapshot or {})
    return text, marks, None, None, None, None
  found = _future_question(question, snapshot)
  if found is not None:
    return found, None, None, None, None, None
  messages = [{'role': 'system', 'content': _system(snapshot or {})}]
  for turn in (history or [])[-6:]:
    role = turn.get('role')
    text = str(turn.get('text') or '').strip()
    if role in ('user', 'assistant') and text:
      messages.append({'role': role, 'content': text})
  messages.append({'role': 'user', 'content': question})
  body = json.dumps({
      'model': MODEL,
      'messages': messages,
      'stream': False,
      'options': {'temperature': 0, 'num_predict': 96},
  }).encode('utf-8')
  request = urllib.request.Request(
      url, data=body, headers={'Content-Type': 'application/json'})
  try:
    with urllib.request.urlopen(request, timeout=timeout) as response:
      payload = json.loads(response.read().decode('utf-8'))
  except urllib.error.URLError as error:
    raise MatchChatError('Phi-4 mini is not running.') from error
  except (json.JSONDecodeError, TimeoutError, ValueError) as error:
    raise MatchChatError('Phi-4 mini did not answer.') from error
  message = payload.get('message') or {}
  text = _visible(message.get('content'))
  if not text:
    raise MatchChatError('Phi-4 mini did not answer.')
  return text, None, None, None, None, None
