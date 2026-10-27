"""Formation shapes and the sentences that ask for them."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import formations

SNAP = {
    'left_name': 'FRQ',
    'right_name': 'RBA',
    'clock': '23:10',
}


# mplsoccer formation codes, scaled from the StatsBomb 120 by 80 pitch:
# x' = x / 60 - 1, y' = (40 - y) / 40. The goalkeeper stays on the goal line.
_PUBLISHED = {
    '4-3-3': [
        ('GK', -1.0, 0.0),
        ('LB', -0.48, 0.75), ('CB', -0.48, 0.25),
        ('CB', -0.48, -0.25), ('RB', -0.48, -0.75),
        ('DM', -0.16, 0.0),
        ('CM', 0.16, 0.40), ('CM', 0.16, -0.40),
        ('LM', 0.48, 0.80), ('CF', 0.80, 0.0), ('RM', 0.48, -0.80),
    ],
    '4-2-3-1': [
        ('GK', -1.0, 0.0),
        ('LB', -0.48, 0.75), ('CB', -0.48, 0.25),
        ('CB', -0.48, -0.25), ('RB', -0.48, -0.75),
        ('DM', -0.16, 0.40), ('DM', -0.16, -0.40),
        ('LM', 0.48, 0.80), ('AM', 0.48, 0.0), ('RM', 0.48, -0.80),
        ('CF', 0.80, 0.0),
    ],
    '4-4-2': [
        ('GK', -1.0, 0.0),
        ('LB', -0.48, 0.75), ('CB', -0.48, 0.25),
        ('CB', -0.48, -0.25), ('RB', -0.48, -0.75),
        ('LM', 0.16, 0.75), ('CM', 0.16, 0.25),
        ('CM', 0.16, -0.25), ('RM', 0.16, -0.75),
        ('CF', 0.80, 0.25), ('CF', 0.80, -0.25),
    ],
    '3-5-2': [
        ('GK', -1.0, 0.0),
        ('CB', -0.48, 0.40), ('CB', -0.48, 0.0), ('CB', -0.48, -0.40),
        ('LM', -0.16, 0.80), ('RM', -0.16, -0.80),
        ('CM', 0.16, 0.40), ('CM', 0.16, 0.0), ('CM', 0.16, -0.40),
        ('CF', 0.80, 0.25), ('CF', 0.80, -0.25),
    ],
    '3-4-2-1': [
        ('GK', -1.0, 0.0),
        ('CB', -0.48, 0.40), ('CB', -0.48, 0.0), ('CB', -0.48, -0.40),
        ('LM', -0.16, 0.75), ('DM', -0.16, 0.25),
        ('DM', -0.16, -0.25), ('RM', -0.16, -0.75),
        ('AM', 0.48, 0.25), ('AM', 0.48, -0.25),
        ('CF', 0.80, 0.0),
    ],
    '4-5-1': [
        ('GK', -1.0, 0.0),
        ('LB', -0.48, 0.75), ('CB', -0.48, 0.25),
        ('CB', -0.48, -0.25), ('RB', -0.48, -0.75),
        ('LM', 0.16, 0.80), ('CM', 0.16, 0.40), ('CM', 0.16, 0.0),
        ('CM', 0.16, -0.40), ('RM', 0.16, -0.80),
        ('CF', 0.80, 0.0),
    ],
}


def test_slots_are_the_published_table():
  names = {value: key for key, value in formations.ROLES.items()}
  for name, expected in _PUBLISHED.items():
    rows = formations.FORMATIONS[name]
    got = [(names[row['role']], row['x'], row['y']) for row in rows]
    assert got == expected, name


def test_shapes_are_elevens():
  assert set(formations.FORMATIONS) == {
      '4-3-3', '4-2-3-1', '4-4-2', '3-5-2', '3-4-2-1', '4-5-1'}
  for name, rows in formations.FORMATIONS.items():
    assert len(rows) == 11, name
    assert rows[0]['role'] == formations.ROLES['GK']
    assert rows[0]['x'] == -1.0


def test_norm_round_trip():
  for side in (-1, 1):
    world_x, world_y = formations.slot_to_world(-0.4, 0.5, side)
    nx, ny = formations.world_to_norm(world_x, world_y, side)
    assert abs(nx - -0.4) < 1e-9
    assert abs(ny - 0.5) < 1e-9
    keeper = formations.slot_to_world(-1, 0, side, keeper=True)
    assert abs(abs(keeper[0]) - formations.PITCH_HALF_W * formations.GK_LINE) < 1e-9
    assert keeper[1] == 0.0


def test_every_shape_reads_as_itself():
  for name in formations.FORMATIONS:
    for side in (-1, 1):
      reason = formations.pitch_shape(name, formations.attack_points(name, side))
      assert reason is None, '%s side %s: %s' % (name, side, reason)
  # The old placement stretched a 4-3-3 from one goal line to the other.
  stretched = [
      (0, 0),
      (16, 26), (16, 9), (16, -9), (16, -26),
      (46, 17), (40, 0), (46, -17),
      (78, 24), (86, 0), (78, -24),
  ]
  reason = formations.pitch_shape('4-3-3', stretched)
  assert reason, 'a stretched 4-3-3 was accepted'


def test_assign_keeps_the_goalkeeper_and_the_nearest_slot():
  shape = formations.FORMATIONS['4-3-3']
  side = -1
  players = []
  for index, row in enumerate(shape):
    x, y = formations.slot_to_world(
        row['x'], row['y'], side, keeper=(index == 0))
    players.append({
        'player': index,
        'role': 'GK' if index == 0 else 'CM',
        'active': True,
        'x': x,
        'y': y,
    })
  players.append({
      'player': 11, 'role': 'CF', 'active': False, 'x': 0.0, 'y': 0.0})
  chosen = formations.assign('4-3-3', players, side)
  assert len(chosen) == 11
  assert chosen[0]['player'] == 0
  assert chosen[0]['role'] == formations.ROLES['GK']
  by_player = {row['player']: row for row in chosen}
  wing = shape[7]
  assert by_player[7]['role'] == wing['role']
  assert by_player[7]['y'] == wing['y']
  assert 11 not in by_player


def test_one_team_and_both():
  one = formations.formation_from_question(
      'put Schmarsenal in a 4-3-3', SNAP)
  assert one['sides'] == {0: '4-3-3'}
  assert one['text'] == 'ARS to 4-3-3 from 23:10.'
  both = formations.formation_from_question(
      'move both teams to a 4-4-2', SNAP)
  assert both['sides'] == {0: '4-4-2', 1: '4-4-2'}
  assert both['text'] == 'Both teams to 4-4-2 from 23:10.'
  split = formations.formation_from_question(
      'put Schman City in a 3-5-2 and Schmarsenal in a 4-2-3-1', SNAP)
  assert split['sides'][1] == '3-5-2'
  assert split['sides'][0] == '4-2-3-1'
  assert 'MNC to 3-5-2' in split['text']
  assert 'ARS to 4-2-3-1' in split['text']
  same = formations.formation_from_question(
      'switch the left team and the right team to 4-5-1', SNAP)
  assert same['sides'] == {0: '4-5-1', 1: '4-5-1'}


def test_missing_team_and_unknown_shape():
  missing = formations.formation_from_question('put them in a 3-4-2-1', SNAP)
  assert missing['sides'] is None
  assert missing['text'] == 'Say which team, or both.'
  unknown = formations.formation_from_question('change to a 5-3-2', SNAP)
  assert unknown['sides'] is None
  assert '4-3-3' in unknown['text']
  assert formations.formation_from_question(
      'what is a 4-3-3', SNAP) is None
  two = formations.formation_from_question(
      'put Schmarsenal in a 4-3-3 or a 4-4-2', SNAP)
  assert two['sides'] is None
  assert 'ARS' in two['text']


def test_pack_drops_a_broken_row():
  packed = formations.pack_entries([
      {'player': 1, 'role': 9, 'x': 0.78001, 'y': -0.2},
      {'player': 'no', 'role': 1, 'x': 0, 'y': 0},
      {'player': 2, 'role': 40, 'x': 0, 'y': 0},
  ])
  assert packed == [{'player': 1, 'role': 9, 'x': 0.78, 'y': -0.2}]


def _visible_metres(player):
  """Metres as the picture shows them. Team 1 is already mirrored here."""
  raw = str(player.position).split(',')
  return (float(raw[0]), float(raw[1]))


def _attack(team, x, y):
  """Depth grows toward the goal this team attacks. Team 1 attacks negative x."""
  if team == 0:
    return (x, y)
  return (-x, -y)


def test_shapes_on_the_pitch():
  """Stand every shape up in the engine and read the players back.

  The placed bodies have to match the slots, and the lines have to still
  read as that shape. A shape stretched the length of the pitch fails.
  """
  from gfootball.env import config as football_config
  from gfootball.env import football_env_core

  configuration = football_config.Config({
      'level': '11_vs_11_stochastic',
      'players': [],
      'action_set': 'full',
      'real_time': False,
      'physics_steps_per_frame': 1,
      'render_resolution_x': 16,
      'render_resolution_y': 16,
      'dump_full_episodes': False,
      'dump_scores': False,
      'reverse_team_processing': False,
  })
  env = football_env_core.FootballEnvCore(configuration)
  env.reset()
  game = env._env
  for _ in range(80):
    game.step()
  origin = env.get_state({})
  try:
    for name in formations.FORMATIONS:
      for team in (0, 1):
        env.set_state(origin)
        rows = formations.slots(name)
        placed = []
        for index, row in enumerate(rows):
          placed.append({
              'player': index,
              'role': row['role'],
              'x': row['x'],
              'y': row['y'],
          })
        side = game.team_side(team)
        game.apply_formation(team, placed, True)
        info = game.get_info()
        players = info.left_team if team == 0 else info.right_team
        points = []
        for index, player in enumerate(players):
          x, y = _visible_metres(player)
          expect_x, expect_y = formations.slot_to_world(
              rows[index]['x'], rows[index]['y'], side, keeper=(index == 0))
          if team == 1:
            expect_x, expect_y = -expect_x, -expect_y
          gap = ((x - expect_x) ** 2 + (y - expect_y) ** 2) ** 0.5
          assert gap < 1.5, '%s team %d player %d is %.1fm away' % (
              name, team, index, gap)
          points.append(_attack(team, x, y))
        reason = formations.pitch_shape(name, points)
        assert reason is None, '%s team %d: %s' % (name, team, reason)
        if name == '4-3-3':
          for _ in range(400):
            game.step()
          info = game.get_info()
          players = info.left_team if team == 0 else info.right_team
          moving = []
          for player in players:
            x, y = _visible_metres(player)
            moving.append(_attack(team, x, y))
          reason = formations.pitch_shape(name, moving, played=True)
          assert reason is None, 'after play, %s team %d: %s' % (
              name, team, reason)
    env.set_state(origin)
    before = formations.pack_entries(game.read_formation(0))
    rows = formations.slots('4-4-2')
    game.apply_formation(0, [
        {'player': index, 'role': row['role'], 'x': row['x'], 'y': row['y']}
        for index, row in enumerate(rows)
    ], True)
    stood = [_visible_metres(player) for player in game.get_info().left_team]
    game.apply_formation(0, before, False)
    for index, player in enumerate(game.get_info().left_team):
      x, y = _visible_metres(player)
      gap = ((x - stood[index][0]) ** 2 + (y - stood[index][1]) ** 2) ** 0.5
      assert gap < 1.5, 'putting the old shape back moved player %d' % index
    assert formations.pack_entries(game.read_formation(0)) == before
  finally:
    env.close()


if __name__ == '__main__':
  test_shapes_are_elevens()
  test_norm_round_trip()
  test_every_shape_reads_as_itself()
  test_assign_keeps_the_goalkeeper_and_the_nearest_slot()
  test_one_team_and_both()
  test_missing_team_and_unknown_shape()
  test_pack_drops_a_broken_row()
  test_shapes_on_the_pitch()
  print('formations ok')
