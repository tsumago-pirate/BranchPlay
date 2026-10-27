"""Saved simulations.

A save is the engine snapshot from the kickoff, the final score, and every
touch in the match. A touch records who did it, what it was, the clock, where
they were, and where the ball was. It is not a reading for every moment.
Opening the snapshot and playing from there repeats the match.

A timeline file keeps another snapshot about once a minute. Scrubbing restores
the latest one at or before the chosen clock and the match runs forward from
there. The kickoff file stays the snapshot used to open the match.

A branch is another timeline from one moment of that match. Its file is named
beside the save. The index lists when it starts, when it ends, and the score.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import os
import struct
import tempfile


def directory():
  return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saves')


def _index_path(folder=None):
  return os.path.join(folder or directory(), 'index.json')


def _state_path(sim_id, folder=None):
  return os.path.join(folder or directory(), '%s.state' % sim_id)


def _touches_path(sim_id, folder=None):
  return os.path.join(folder or directory(), '%s.touches.json' % sim_id)


def _timeline_path(sim_id, folder=None):
  return os.path.join(folder or directory(), '%s.timeline' % sim_id)


def _moments_path(sim_id, folder=None):
  return os.path.join(folder or directory(), '%s.moments.json' % sim_id)


_TIMELINE_MAGIC = b'BPT1'


def clock_seconds(clock):
  """Match clock as seconds. A clock is MM:SS. A number is already seconds."""
  if isinstance(clock, bool):
    return 0
  if isinstance(clock, int):
    return clock
  text = str(clock or '').strip()
  parts = text.split(':')
  if len(parts) != 2:
    return 0
  try:
    return int(parts[0]) * 60 + int(parts[1])
  except ValueError:
    return 0


def clock_from_step(step):
  """Scoreboard seconds for an in-play step.

  The drawn clock gains 9 seconds every 50 steps. Step 30,000 is 90:00.
  The text on the feed only changes when a frame is drawn, so seeking uses
  the step.
  """
  try:
    step = int(step)
  except (TypeError, ValueError):
    return 0
  if step < 0:
    return 0
  return step * 9 // 50


def step_for_clock(seconds):
  """First in-play step at which the scoreboard shows this second."""
  try:
    seconds = int(seconds)
  except (TypeError, ValueError):
    return 0
  if seconds <= 0:
    return 0
  return (seconds * 50 + 8) // 9


def write_timeline(sim_id, marks, end_step, end_clock, folder=None):
  """Store the minute snapshots and the clock the match ended on."""
  folder = folder or directory()
  os.makedirs(folder, exist_ok=True)
  rows = []
  for row in marks or []:
    if not isinstance(row, dict):
      continue
    blob = row.get('state')
    blob = blob if isinstance(blob, (bytes, bytearray)) else bytes(blob or b'')
    if not blob:
      continue
    rows.append((int(row.get('step', 0)), int(row.get('clock') or 0), bytes(blob)))
  payload = bytearray()
  payload += _TIMELINE_MAGIC
  payload += struct.pack('<IiI', len(rows), int(end_step), int(end_clock))
  for step, clock, blob in rows:
    payload += struct.pack('<iII', step, clock, len(blob))
    payload += blob
  target = _timeline_path(sim_id, folder)
  temporary = target + '.tmp'
  with open(temporary, 'wb') as handle:
    handle.write(payload)
  os.replace(temporary, target)
  return target


def read_timeline(sim_id, folder=None):
  """Minute snapshots, or None when this save has no timeline."""
  path = _timeline_path(sim_id, folder)
  try:
    with open(path, 'rb') as handle:
      payload = handle.read()
  except OSError:
    return None
  if len(payload) < 16 or payload[:4] != _TIMELINE_MAGIC:
    return None
  count, end_step, end_clock = struct.unpack_from('<IiI', payload, 4)
  cursor = 16
  marks = []
  for _ in range(count):
    if cursor + 12 > len(payload):
      return None
    step, clock, size = struct.unpack_from('<iII', payload, cursor)
    cursor += 12
    if size < 0 or cursor + size > len(payload):
      return None
    marks.append({
        'step': step,
        'clock': clock,
        'state': payload[cursor:cursor + size],
    })
    cursor += size
  if not marks:
    return None
  return {'end_step': end_step, 'end_clock': end_clock, 'marks': marks}


def _clean_moment_rows(rows):
  clean = []
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    try:
      start = int(row.get('start'))
      end = int(row.get('end'))
    except (TypeError, ValueError):
      continue
    if end < start:
      continue
    clean.append({'start': start, 'end': end})
  return clean


def _moment_map(rows):
  """A list is the base match. A dict is one list per timeline. '' is the base."""
  if isinstance(rows, list):
    rows = {'': rows}
  mapped = {}
  for key, group in (rows or {}).items():
    clean = _clean_moment_rows(group)
    if clean:
      mapped[str(key or '')] = clean
  return mapped


def write_moments(sim_id, rows, folder=None):
  """Keep highlighted key moments with this save, one list per timeline.

  An empty result removes the file. '' is the base match.
  """
  path = _moments_path(sim_id, folder)
  mapped = _moment_map(rows)
  if not mapped:
    try:
      os.remove(path)
    except OSError:
      pass
    return
  folder = folder or directory()
  os.makedirs(folder, exist_ok=True)
  target = _moments_path(sim_id, folder)
  temporary = target + '.tmp'
  with open(temporary, 'w') as handle:
    json.dump(mapped, handle)
  os.replace(temporary, target)


def read_moments(sim_id, folder=None):
  """Key moments by timeline. '' is the base match. Empty when none were kept.

  An older file is one list and belongs to the base match.
  """
  path = _moments_path(sim_id, folder)
  try:
    with open(path, 'r') as handle:
      payload = json.load(handle)
  except (OSError, ValueError):
    return {}
  if isinstance(payload, list):
    payload = {'': payload}
  if not isinstance(payload, dict):
    return {}
  return _moment_map(payload)


def _branches_path(sim_id, folder=None):
  return os.path.join(folder or directory(), '%s.branches.json' % sim_id)


def _branch_key(sim_id, branch_id):
  return '%s.b%s' % (sim_id, branch_id)


def _read_branch_index(sim_id, folder=None):
  path = _branches_path(sim_id, folder)
  try:
    with open(path, 'r', encoding='utf-8') as handle:
      raw = json.load(handle)
  except (OSError, ValueError):
    return []
  rows = []
  for row in raw.get('branches') or []:
    if not isinstance(row, dict) or not row.get('id'):
      continue
    score = row.get('score') or [0, 0]
    try:
      score = [int(score[0]), int(score[1])]
    except (TypeError, ValueError, IndexError):
      score = [0, 0]
    minutes = row.get('minutes')
    try:
      minutes = None if minutes is None else int(minutes)
    except (TypeError, ValueError):
      minutes = None
    parent = row.get('parent') or None
    item = {
        'id': str(row['id']),
        'parent': None if not parent else str(parent),
        'clock': int(row.get('clock') or 0),
        'step': int(row.get('step') or 0),
        'end_clock': int(row.get('end_clock') or 0),
        'end_step': int(row.get('end_step') or 0),
        'minutes': minutes,
        'score': score,
        'seed': int(row.get('seed') or 0),
        'on_timeline': row.get('on_timeline') if 'on_timeline' in row else None,
    }
    shape = _formation_map(row.get('formation'))
    if shape:
      item['formation'] = shape
    added = _added_rows(row.get('added'))
    if added:
      item['added'] = added
    rows.append(item)
  return rows


def _write_index(rows, folder):
  """Replace the saved-simulation list. The caller already filtered the rows."""
  folder = folder or directory()
  os.makedirs(folder, exist_ok=True)
  path = _index_path(folder)
  payload = json.dumps({'simulations': rows}).encode('utf-8')
  descriptor, temporary = tempfile.mkstemp(dir=folder, suffix='.json')
  try:
    with os.fdopen(descriptor, 'wb') as handle:
      handle.write(payload)
    os.replace(temporary, path)
  except Exception:
    try:
      os.unlink(temporary)
    except OSError:
      pass
    raise


def _write_branch_index(sim_id, rows, folder):
  path = _branches_path(sim_id, folder)
  payload = json.dumps({'branches': rows}).encode('utf-8')
  descriptor, temporary = tempfile.mkstemp(dir=folder, suffix='.json')
  try:
    with os.fdopen(descriptor, 'wb') as handle:
      handle.write(payload)
    os.replace(temporary, path)
  except Exception:
    try:
      os.unlink(temporary)
    except OSError:
      pass
    raise


def write_branch(sim_id, branch, folder=None):
  """Store one branch timeline and add it to that save's branch list."""
  folder = folder or directory()
  os.makedirs(folder, exist_ok=True)
  branch_id = str(branch['id'])
  key = _branch_key(sim_id, branch_id)
  write_timeline(
      key, branch.get('marks'), branch.get('end_step'), branch.get('end_clock'),
      folder)
  kept = []
  for row in branch.get('touches') or []:
    touch = _touch_row(row)
    if touch:
      kept.append(touch)
  touch_path = _touches_path(key, folder)
  touch_temp = touch_path + '.tmp'
  with open(touch_temp, 'w', encoding='utf-8') as handle:
    json.dump({'touches': kept}, handle, separators=(',', ':'))
  os.replace(touch_temp, touch_path)
  score = branch.get('score') or [0, 0]
  minutes = branch.get('minutes')
  parent = branch.get('parent') or None
  meta = {
      'id': branch_id,
      'parent': None if not parent else str(parent),
      'clock': int(branch.get('clock') or 0),
      'step': int(branch.get('step') or 0),
      'end_clock': int(branch.get('end_clock') or 0),
      'end_step': int(branch.get('end_step') or 0),
      'minutes': None if minutes is None else int(minutes),
      'score': [int(score[0]), int(score[1])],
      'seed': int(branch.get('seed') or 0),
      'on_timeline': branch.get('on_timeline', True) is not False,
  }
  shape = _formation_map(branch.get('formation'))
  if shape:
    meta['formation'] = shape
  added = _added_rows(branch.get('added'))
  if added:
    meta['added'] = added
  rows = [row for row in _read_branch_index(sim_id, folder) if row['id'] != branch_id]
  rows.append(meta)
  _write_branch_index(sim_id, rows, folder)
  return meta


def _formation_map(raw):
  """Both teams' slots, or None when this branch did not change a shape."""
  if not isinstance(raw, dict):
    return None
  kept = {}
  for key, rows in raw.items():
    try:
      team = int(key)
    except (TypeError, ValueError):
      continue
    if team not in (0, 1) or not isinstance(rows, list):
      continue
    slots = []
    for row in rows:
      if not isinstance(row, dict):
        continue
      try:
        role = int(row['role'])
        slot = {
            'player': int(row['player']),
            'role': role,
            'x': round(float(row['x']), 4),
            'y': round(float(row['y']), 4),
        }
      except (TypeError, ValueError, KeyError):
        continue
      if role < 0 or role > 9:
        continue
      slots.append(slot)
    if slots:
      kept[str(team)] = slots
  return kept or None


def _added_rows(raw):
  """Extra players stored with a branch. Empty when that branch added none."""
  if not isinstance(raw, list):
    return []
  rows = []
  for item in raw:
    if not isinstance(item, dict):
      continue
    try:
      team = int(item['team'])
      shirt = int(item['shirt'])
      role = int(item.get('role') or 0)
      name = str(item['name'])
      slot_x = round(float(item.get('x') or 0), 4)
      slot_y = round(float(item.get('y') or 0), 4)
    except (TypeError, ValueError, KeyError):
      continue
    if team not in (0, 1) or shirt < 1 or shirt > 99 or not name:
      continue
    if role < 0 or role > 9:
      role = 5
    rows.append({
        'team': team,
        'name': name,
        'shirt': shirt,
        'x': slot_x,
        'y': slot_y,
        'role': role,
    })
  return rows


def shows_on_timeline(row):
  """False for a key-moment branch. Those are saved and kept off the timeline."""
  flag = (row or {}).get('on_timeline')
  if flag is False:
    return False
  if flag is True:
    return True
  if (row or {}).get('minutes') is not None:
    return True
  span = int((row or {}).get('end_clock') or 0) - int((row or {}).get('clock') or 0)
  return span <= 0 or span > 90


def clear_branches(sim_id, folder=None):
  """Remove every branch of this save. The match itself stays."""
  folder = folder or directory()
  rows = _read_branch_index(sim_id, folder)
  for row in rows:
    key = _branch_key(sim_id, row['id'])
    for path in (_timeline_path(key, folder), _touches_path(key, folder)):
      try:
        os.remove(path)
      except OSError:
        pass
  try:
    os.remove(_branches_path(sim_id, folder))
  except OSError:
    pass
  return len(rows)


def read_branches(sim_id, folder=None):
  """Each saved branch, with its minute snapshots and its own touches."""
  loaded = []
  for meta in _read_branch_index(sim_id, folder):
    timeline = read_timeline(_branch_key(sim_id, meta['id']), folder)
    if not timeline:
      continue
    touches = read_touches(_branch_key(sim_id, meta['id']), folder) or []
    row = dict(meta)
    row['marks'] = timeline['marks']
    row['touches'] = touches
    row['end_step'] = timeline['end_step']
    row['end_clock'] = timeline['end_clock']
    loaded.append(row)
  return loaded


def pick_checkpoint(marks, seconds):
  """The latest snapshot at or before this match clock."""
  chosen = marks[0]
  for row in marks:
    if int(row['clock']) <= int(seconds):
      chosen = row
    else:
      break
  return chosen


def scrub_plan(current_step, target_step, checkpoint_step):
  """Forward when the picture is already between this snapshot and the target."""
  if int(checkpoint_step) <= int(current_step) <= int(target_step):
    return 'forward'
  return 'restore'


def _touch_row(row):
  if not isinstance(row, dict):
    return None
  try:
    return {
        'team': int(row['team']),
        'shirt': int(row['shirt']),
        'name': str(row.get('name') or ''),
        'action': str(row.get('action') or ''),
        'clock': str(row.get('clock') or ''),
        'x': round(float(row.get('x') or 0), 1),
        'y': round(float(row.get('y') or 0), 1),
        'speed': round(float(row.get('speed') or 0), 1),
        'ball_x': round(float(row.get('ball_x') or 0), 1),
        'ball_y': round(float(row.get('ball_y') or 0), 1),
        'ball_speed': round(float(row.get('ball_speed') or 0), 1),
    }
  except (TypeError, ValueError, KeyError):
    return None


def list_simulations(folder=None):
  """Newest first. Rows are id, team names, and the final score."""
  path = _index_path(folder)
  try:
    with open(path, 'r', encoding='utf-8') as handle:
      raw = json.load(handle)
  except (OSError, ValueError):
    return []
  rows = []
  for row in raw.get('simulations') or []:
    if not isinstance(row, dict) or not row.get('id'):
      continue
    score = row.get('score') or [0, 0]
    try:
      score = [int(score[0]), int(score[1])]
    except (TypeError, ValueError, IndexError):
      score = [0, 0]
    rows.append({
        'id': str(row['id']),
        'left': str(row.get('left') or ''),
        'right': str(row.get('right') or ''),
        'score': score,
        'deterministic': bool(row.get('deterministic')),
    })
  return rows


def write_simulation(sim_id, state, left, right, score, touches=None, folder=None,
                     deterministic=False):
  """Store one kickoff snapshot, its touches, and add it to the front of the list."""
  folder = folder or directory()
  os.makedirs(folder, exist_ok=True)
  blob = state if isinstance(state, (bytes, bytearray)) else bytes(state)
  target = _state_path(sim_id, folder)
  temporary = target + '.tmp'
  with open(temporary, 'wb') as handle:
    handle.write(blob)
  os.replace(temporary, target)
  kept = []
  for row in touches or []:
    touch = _touch_row(row)
    if touch:
      kept.append(touch)
  touch_path = _touches_path(sim_id, folder)
  touch_temp = touch_path + '.tmp'
  with open(touch_temp, 'w', encoding='utf-8') as handle:
    json.dump({'touches': kept}, handle, separators=(',', ':'))
  os.replace(touch_temp, touch_path)
  rows = [row for row in list_simulations(folder) if row['id'] != sim_id]
  rows.insert(0, {
      'id': sim_id,
      'left': left,
      'right': right,
      'score': [int(score[0]), int(score[1])],
      'deterministic': bool(deterministic),
  })
  _write_index(rows, folder)
  return target


def delete_simulation(sim_id, folder=None):
  """Remove one save, its timeline, and its branches. False when it is not listed."""
  sim_id = str(sim_id or '')
  if not sim_id or sim_id in ('.', '..') or '/' in sim_id or '\\' in sim_id:
    return False
  folder = folder or directory()
  rows = list_simulations(folder)
  if not any(row['id'] == sim_id for row in rows):
    return False
  clear_branches(sim_id, folder)
  for path in (
      _state_path(sim_id, folder),
      _touches_path(sim_id, folder),
      _timeline_path(sim_id, folder),
      _moments_path(sim_id, folder),
  ):
    try:
      os.remove(path)
    except OSError:
      pass
  _write_index([row for row in rows if row['id'] != sim_id], folder)
  return True


def read_simulation(sim_id, folder=None):
  """The kickoff snapshot, or None when that save is not on disk."""
  path = _state_path(sim_id, folder)
  try:
    with open(path, 'rb') as handle:
      return handle.read()
  except OSError:
    return None


def read_touches(sim_id, folder=None):
  """The touch list, or None when that save has no list."""
  path = _touches_path(sim_id, folder)
  try:
    with open(path, 'r', encoding='utf-8') as handle:
      raw = json.load(handle)
  except (OSError, ValueError):
    return None
  rows = []
  for row in raw.get('touches') or []:
    touch = _touch_row(row)
    if touch:
      rows.append(touch)
  return rows
