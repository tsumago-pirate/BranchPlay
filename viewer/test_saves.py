"""The saved-simulation list."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import os
import tempfile

import saves


def test_round_trip():
  folder = tempfile.mkdtemp()
  saves.write_simulation('20261025-144800', b'kickoff', 'FRQ', 'RBA', [1, 0], [
      {'team': 0, 'shirt': 9, 'name': 'Haaland', 'action': 'SHOT', 'clock': '12:03',
       'x': 18.2, 'y': -1.4, 'speed': 6.1, 'ball_x': 18.0, 'ball_y': -1.2, 'ball_speed': 22.4},
  ], folder)
  saves.write_simulation('20261025-150000', b'later', 'FRQ', 'RBA', [0, 2], folder=folder)
  rows = saves.list_simulations(folder)
  assert [row['id'] for row in rows] == ['20261025-150000', '20261025-144800']
  assert rows[1]['score'] == [1, 0]
  assert saves.read_simulation('20261025-144800', folder) == b'kickoff'
  touches = saves.read_touches('20261025-144800', folder)
  assert len(touches) == 1 and touches[0]['action'] == 'SHOT'
  assert touches[0]['ball_speed'] == 22.4
  assert saves.read_touches('20261025-150000', folder) == []
  assert saves.read_simulation('missing', folder) is None
  assert os.path.isfile(os.path.join(folder, 'index.json'))
  assert saves.read_timeline('20261025-144800', folder) is None


def test_timeline():
  folder = tempfile.mkdtemp()
  marks = [
      {'step': -1, 'clock': 0, 'state': b'kick'},
      {'step': 400, 'clock': 72, 'state': b'minute-one'},
      {'step': 800, 'clock': 130, 'state': b'minute-two'},
  ]
  saves.write_timeline('20261025-160000', marks, 30000, 5412, folder)
  timeline = saves.read_timeline('20261025-160000', folder)
  assert timeline['end_step'] == 30000
  assert timeline['end_clock'] == 5412
  assert [row['state'] for row in timeline['marks']] == [
      b'kick', b'minute-one', b'minute-two']
  assert saves.pick_checkpoint(timeline['marks'], 0)['step'] == -1
  assert saves.pick_checkpoint(timeline['marks'], 100)['clock'] == 72
  assert saves.pick_checkpoint(timeline['marks'], 5412)['clock'] == 130
  assert saves.scrub_plan(500, 600, 400) == 'forward'
  assert saves.scrub_plan(900, 400, 400) == 'restore'
  assert saves.clock_from_step(30000) == 90 * 60
  assert saves.clock_from_step(1589) == 286
  assert saves.step_for_clock(286) == 1589
  assert saves.clock_seconds('45:30') == 45 * 60 + 30
  assert saves.clock_seconds(12) == 12
  broken = os.path.join(folder, '20261025-160000.timeline')
  with open(broken, 'wb') as handle:
    handle.write(b'nope')
  assert saves.read_timeline('20261025-160000', folder) is None


def test_branch_round_trip():
  folder = tempfile.mkdtemp()
  saves.write_simulation(
      '20261025-170000', b'kickoff', 'FRQ', 'RBA', [1, 0], folder=folder,
      deterministic=True)
  saves.write_simulation(
      '20261025-170100', b'later', 'FRQ', 'RBA', [0, 0], folder=folder)
  rows = saves.list_simulations(folder)
  assert rows[1]['deterministic'] is True
  assert rows[0]['deterministic'] is False
  touch = {
      'team': 0, 'shirt': 7, 'name': 'Saka', 'action': 'SHOT', 'clock': '12:40',
      'x': 10.0, 'y': 1.0, 'speed': 4.0, 'ball_x': 11.0, 'ball_y': 1.0,
      'ball_speed': 18.0,
  }
  saves.write_branch('20261025-170000', {
      'id': '1',
      'parent': None,
      'clock': 760,
      'step': 4222,
      'end_clock': 900,
      'end_step': 5000,
      'minutes': 2,
      'score': [2, 0],
      'seed': 99,
      'marks': [{'step': 4222, 'clock': 760, 'state': b'fork'}],
      'touches': [touch],
  }, folder)
  loaded = saves.read_branches('20261025-170000', folder)
  assert len(loaded) == 1
  assert loaded[0]['id'] == '1'
  assert loaded[0]['minutes'] == 2
  assert loaded[0]['score'] == [2, 0]
  assert loaded[0]['marks'][0]['state'] == b'fork'
  assert loaded[0]['touches'][0]['action'] == 'SHOT'
  assert 'formation' not in loaded[0]
  assert 'added' not in loaded[0]
  saves.write_branch('20261025-170000', {
      'id': '2',
      'parent': '1',
      'clock': 760,
      'step': 4222,
      'end_clock': 5400,
      'end_step': 30000,
      'minutes': None,
      'score': [2, 1],
      'seed': 100,
      'on_timeline': True,
      'marks': [{'step': 4222, 'clock': 760, 'state': b'shape'}],
      'touches': [],
      'formation': {
          '0': [{'player': 9, 'role': 9, 'x': 0.78001, 'y': 0.0}],
          '1': [{'player': 0, 'role': 0, 'x': -1, 'y': 0}],
          'nope': [{'player': 1, 'role': 1, 'x': 0, 'y': 0}],
      },
  }, folder)
  shaped = saves.read_branches('20261025-170000', folder)
  assert shaped[1]['formation']['0'][0]['x'] == 0.78
  assert shaped[1]['formation']['1'][0]['role'] == 0
  assert 'nope' not in shaped[1]['formation']
  assert saves.shows_on_timeline(shaped[1]) is True
  saves.write_branch('20261025-170000', {
      'id': '3',
      'parent': '1',
      'clock': 760,
      'step': 4222,
      'end_clock': 5400,
      'end_step': 30000,
      'minutes': None,
      'score': [2, 1],
      'seed': 101,
      'on_timeline': True,
      'marks': [{'step': 4222, 'clock': 760, 'state': b'added'}],
      'touches': [],
      'added': [
          {'team': 0, 'name': 'Schmarsenal', 'shirt': 12, 'x': 0.2, 'y': -0.1, 'role': 5},
          {'team': 'no', 'name': 'Skip', 'shirt': 13, 'x': 0, 'y': 0, 'role': 5},
      ],
  }, folder)
  with_player = saves.read_branches('20261025-170000', folder)
  assert with_player[2]['added'] == [{
      'team': 0, 'name': 'Schmarsenal', 'shirt': 12, 'x': 0.2, 'y': -0.1, 'role': 5,
  }]
  assert saves.read_branches('20261025-170100', folder) == []
  assert saves.clear_branches('20261025-170000', folder) == 3
  assert saves.read_branches('20261025-170000', folder) == []
  assert saves.clear_branches('20261025-170000', folder) == 0
  assert saves.shows_on_timeline({'minutes': 2, 'clock': 0, 'end_clock': 120}) is True
  assert saves.shows_on_timeline({'minutes': None, 'clock': 283, 'end_clock': 343, 'on_timeline': False}) is False
  assert saves.shows_on_timeline({'minutes': None, 'clock': 283, 'end_clock': 313}) is False
  assert saves.shows_on_timeline({'minutes': None, 'clock': 296, 'end_clock': 5400}) is True


def test_moments_round_trip():
  folder = tempfile.mkdtemp()
  saves.write_moments('20261025-180000', [
      {'start': 11, 'end': 71},
      {'start': 'no', 'end': 3},
      {'start': 90, 'end': 40},
  ], folder)
  assert saves.read_moments('20261025-180000', folder) == {'': [{'start': 11, 'end': 71}]}
  saves.write_moments('20261025-180000', {
      '': [{'start': 11, 'end': 71}],
      '4': [{'start': 20, 'end': 40}, {'start': 9, 'end': 1}],
  }, folder)
  assert saves.read_moments('20261025-180000', folder) == {
      '': [{'start': 11, 'end': 71}],
      '4': [{'start': 20, 'end': 40}],
  }
  legacy = os.path.join(folder, '20261025-180000.moments.json')
  with open(legacy, 'w') as handle:
    json.dump([{'start': 3, 'end': 8}], handle)
  assert saves.read_moments('20261025-180000', folder) == {'': [{'start': 3, 'end': 8}]}
  saves.write_moments('20261025-180000', [], folder)
  assert saves.read_moments('20261025-180000', folder) == {}
  assert saves.read_moments('missing', folder) == {}


def test_delete_simulation():
  folder = tempfile.mkdtemp()
  saves.write_simulation('20261025-180100', b'one', 'FRQ', 'RBA', [1, 0], folder=folder)
  saves.write_simulation('20261025-180200', b'two', 'FRQ', 'RBA', [0, 1], folder=folder)
  saves.write_timeline(
      '20261025-180200', [{'step': 0, 'clock': 0, 'state': b'k'}], 10, 1, folder)
  saves.write_moments('20261025-180200', [{'start': 1, 'end': 2}], folder)
  saves.write_branch('20261025-180200', {
      'id': '1',
      'clock': 10,
      'step': 20,
      'end_clock': 70,
      'end_step': 80,
      'minutes': 1,
      'score': [1, 0],
      'seed': 3,
      'marks': [{'step': 20, 'clock': 10, 'state': b'fork'}],
      'touches': [],
  }, folder)
  assert saves.delete_simulation('20261025-180200', folder) is True
  assert [row['id'] for row in saves.list_simulations(folder)] == ['20261025-180100']
  assert saves.read_simulation('20261025-180200', folder) is None
  assert saves.read_simulation('20261025-180100', folder) == b'one'
  assert saves.read_timeline('20261025-180200', folder) is None
  assert saves.read_moments('20261025-180200', folder) == {}
  assert saves.read_branches('20261025-180200', folder) == []
  assert not os.path.exists(os.path.join(folder, '20261025-180200.branches.json'))
  assert not os.path.exists(os.path.join(folder, '20261025-180200.b1.timeline'))
  assert saves.delete_simulation('missing', folder) is False
  assert saves.delete_simulation('../index', folder) is False
  assert [row['id'] for row in saves.list_simulations(folder)] == ['20261025-180100']


if __name__ == '__main__':
  test_round_trip()
  test_timeline()
  test_branch_round_trip()
  test_moments_round_trip()
  test_delete_simulation()
  print('saves ok')
