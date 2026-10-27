"""The match chat filter and the facts it is willing to quote."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import match_chat


def player(**kwargs):
  row = {
      'team': 0,
      'player': 0,
      'name': 'Silva',
      'shirt': 4,
      'role': 'CB',
      'x': -20.0,
      'y': 0.0,
      'speed': 2.0,
      'tired': 0.1,
      'active': True,
      'ball': False,
      'touches': 1,
  }
  row.update(kwargs)
  return row


def test_role_and_team():
  roster = [
      player(),
      player(team=1, player=3, name='Dias', shirt=5, role='CB', x=20, y=2),
      player(player=9, name='Haaland', shirt=9, role='CF', x=10, y=0, speed=7),
  ]
  picked = match_chat.select_players(roster, {'team': 'right', 'role': 'CB'})
  assert [row['name'] for row in picked] == ['Dias']


def test_fastest_on_a_side():
  roster = [
      player(player=1, name='Slow', speed=1),
      player(player=2, name='Quick', shirt=2, role='CM', speed=8, x=-5),
  ]
  picked = match_chat.select_players(roster, {'team': 'left', 'stat': 'fastest'})
  assert [row['name'] for row in picked] == ['Quick']


def test_zones_and_ball():
  roster = [
      player(player=1, name='Home', x=-30, y=0),
      player(player=2, name='Wide', shirt=11, role='LM', x=-10, y=25),
      player(player=3, name='Near', shirt=8, role='CM', x=2, y=1),
  ]
  own = match_chat.select_players(roster, {'zone': 'own_half'})
  assert {row['name'] for row in own} == {'Home', 'Wide'}
  wide = match_chat.select_players(roster, {'zone': 'wide'})
  assert [row['name'] for row in wide] == ['Wide']
  near = match_chat.select_players(roster, {'zone': 'near_ball'}, ball=(0, 0))
  assert [row['name'] for row in near] == ['Near']


def test_inactive_and_empty_are_not_boxed():
  roster = [player(active=False, role='GK', name='Keeper', shirt=1)]
  assert match_chat.select_players(roster, {'role': 'GK'}) == []
  assert match_chat.select_players(roster, {}) == []
  assert match_chat.select_players(roster, {'team': 'both'}) == []


def test_shirt_and_name():
  roster = [
      player(player=1, name='Silva', shirt=4),
      player(team=1, player=2, name='Silva', shirt=4, x=15),
      player(player=9, name='Haaland', shirt=9, role='CF'),
  ]
  both = match_chat.select_players(roster, {'name': 'sil'})
  assert len(both) == 2
  one = match_chat.select_players(roster, {'name': 'haaland', 'shirt': 9})
  assert [row['player'] for row in one] == [9]


def test_snapshot_uses_the_log_and_the_scoreboard_names():
  text = match_chat.snapshot_text({
      'left_name': 'FRQ',
      'right_name': 'RBA',
      'score': [1, 0],
      'clock': '12:04',
      'speed': 14.2,
      'ball': [3.0, -1.0],
      'roster': [player(name='Silva')],
      'log': [{'team': 0, 'shirt': 4, 'action': 'SHORT PASS', 'clock': '12:03'}],
  })
  assert 'ARS 1' in text
  assert 'MNC 0' in text
  assert '12:03 ARS 4 short pass' in text
  assert 'FRQ' not in text
  assert 'goal' not in text.lower()


def _passes(team, shirt, action, count, clock='10:00'):
  return [{'team': team, 'shirt': shirt, 'action': action, 'clock': clock}
          for _ in range(count)]


def test_record_counts_the_whole_log():
  roster = [
      player(player=1, name='Even', shirt=4),
      player(player=9, name='Haaland', shirt=9, role='CF'),
  ]
  log = _passes(0, 9, 'SHORT PASS', 7) + _passes(0, 9, 'LONG PASS', 1, '10:08')
  log += _passes(0, 9, 'CONTROL', 3, '10:09')
  log += _passes(0, 4, 'HIGH PASS', 8, '11:00')
  rows = {row['shirt']: row for row in match_chat.player_record(roster, log, (0, 0))}
  assert rows[9]['passes'] == 8
  assert rows[9]['short_pass'] == 7
  assert rows[9]['long_pass'] == 1
  assert rows[9]['control'] == 3
  assert rows[9]['touches'] == 11
  assert rows[9]['last_action'] == 'control'
  assert rows[4]['passes'] == 8
  assert rows[4]['high_pass'] == 8
  text = match_chat.snapshot_text({
      'left_name': 'FRQ', 'right_name': 'RBA', 'score': [0, 0],
      'clock': '12:00', 'speed': 1, 'ball': [0, 0],
      'roster': roster, 'log': log,
  })
  header, row = text.splitlines()[3], text.splitlines()[4]
  assert len(header.split()) == len(row.split())
  assert 'passes' in header
  assert 'goal' not in text.lower()


def test_odd_shirts_and_pass_counts():
  roster = [
      player(player=1, name='Even', shirt=4),
      player(player=9, name='Haaland', shirt=9, role='CF'),
      player(team=1, player=3, name='Dias', shirt=5, role='CB', x=20),
  ]
  log = _passes(0, 9, 'SHORT PASS', 7) + _passes(0, 9, 'LONG PASS', 1)
  log += _passes(0, 4, 'HIGH PASS', 8)
  snapshot = {
      'left_name': 'FRQ',
      'right_name': 'RBA',
      'roster': roster,
      'log': log,
      'ball': [0, 0],
  }
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'Highlight people who had odd number shirts', snapshot)
  assert 'Dias' in text and 'Haaland' in text and 'Even' not in text
  assert {mark['player'] for mark in marks} == {9, 3}
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'Highlight everyone who had completed 8 or more pass up until that point',
      snapshot)
  assert {mark['player'] for mark in marks} == {1, 9}
  short = match_chat.highlight_from_question('Box players with 3 or more short passes')
  assert short['where'] == [{'field': 'short_pass', 'op': '>=', 'value': 3}]
  assert match_chat.highlight_from_question('Highlight shirt 9') == {'shirt': 9}
  few = match_chat.answer(
      'Highlight players with 8 or more passes',
      {'roster': [player(shirt=9)], 'log': _passes(0, 9, 'SHORT PASS', 7),
       'left_name': 'ARS', 'right_name': 'MNC'})
  assert few[1] == []


def test_most_dribbles():
  question = 'highlight the player with the most dribbles'
  assert match_chat.highlight_from_question(question) == {
      'rank': {'how': 'most', 'field': 'control'}}
  roster = [
      player(player=1, name='Quiet', shirt=4),
      player(player=8, name='Dribbler', shirt=8, role='CM'),
      player(player=9, name='Passer', shirt=9, role='CF'),
  ]
  log = (_passes(0, 8, 'CONTROL', 4) + _passes(0, 9, 'SHORT PASS', 6)
         + _passes(0, 4, 'CONTROL', 1))
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(question, {
      'left_name': 'ARS',
      'right_name': 'MNC',
      'roster': roster,
      'log': log,
  })
  assert marks == [{'team': 0, 'player': 8}]
  assert 'Dribbler' in text
  fewest = match_chat.highlight_from_question('Highlight the player with the fewest shots')
  assert fewest['rank'] == {'how': 'fewest', 'field': 'shot'}


def test_long_passed_and_everyone():
  spec = match_chat.highlight_from_question(
      'highlight all players who have long passed')
  assert spec['where'] == [{'field': 'long_pass', 'op': '>=', 'value': 1}]
  assert 'everyone' not in spec
  roster = [
      player(player=1, name='Long', shirt=7),
      player(player=2, name='Short', shirt=8),
      player(player=3, name='Quiet', shirt=9),
  ]
  log = _passes(0, 7, 'LONG PASS', 2) + _passes(0, 8, 'SHORT PASS', 3)
  snapshot = {
      'left_name': 'ARS', 'right_name': 'MNC', 'roster': roster, 'log': log,
  }
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'highlight all players who have long passed', snapshot)
  assert marks == [{'team': 0, 'player': 1}]
  assert 'Long' in text and 'Short' not in text
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer('highlight all players', snapshot)
  assert {mark['player'] for mark in marks} == {1, 2, 3}
  assert text == 'Boxed every player.'
  many = [player(player=i, name='P%s' % i, shirt=i) for i in (1, 2, 3)]
  counted = match_chat.describe_highlight(
      many, {'where': [{'field': 'shot', 'op': '>=', 'value': 1}]}, 'ARS', 'MNC')
  assert counted == 'Boxed 3 players.'
  dribbled = match_chat.highlight_from_question(
      'highlight players who have dribbled')
  assert dribbled['where'] == [{'field': 'control', 'op': '>=', 'value': 1}]


def test_fullbacks_are_not_the_whole_side():
  roster = [
      player(team=1, player=1, name='Walker', shirt=2, role='RB'),
      player(team=1, player=2, name='Ake', shirt=6, role='LB'),
      player(team=1, player=3, name='Dias', shirt=3, role='CB'),
      player(team=1, player=4, name='Haaland', shirt=9, role='CF'),
      player(player=5, name='Timber', shirt=12, role='RB'),
  ]
  snap = {'left_name': 'FRQ', 'right_name': 'RBA', 'roster': roster, 'log': []}
  spec = match_chat.highlight_from_question('box schman city fullbacks', snap)
  assert spec['team'] == 'right'
  assert spec['roles'] == ['LB', 'RB']
  assert 'role' not in spec
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'box schman city fullbacks', snap)
  assert {mark['player'] for mark in marks} == {1, 2}
  assert all(mark['team'] == 1 for mark in marks)
  assert 'Walker' in text and 'Ake' in text
  assert 'Dias' not in text and 'Haaland' not in text and 'Timber' not in text
  both = match_chat.highlight_from_question('box the full backs')
  assert both['roles'] == ['LB', 'RB']
  assert 'team' not in both


def test_club_names_pick_a_side():
  spec = match_chat.highlight_from_question('highlight all schmarsenal players')
  assert spec['team'] == 'left'
  assert 'everyone' not in spec
  roster = [
      player(player=1, name='Ramsdale', shirt=1),
      player(player=2, name='Saliba', shirt=2),
      player(team=1, player=1, name='Ederson', shirt=31, x=10),
  ]
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer('box all schman city players', {
      'left_name': 'FRQ',
      'right_name': 'RBA',
      'roster': roster,
      'log': [],
  })
  assert marks == [{'team': 1, 'player': 1}]
  assert 'Ederson' in text
  assert 'Ramsdale' not in text
  assert match_chat.highlight_from_question('box all schmen city players')['team'] == 'right'


def test_question_picks_the_boxes():
  assert match_chat.highlight_from_question('Who made the last touch?') is None
  assert match_chat.highlight_from_question('Highlight the goalkeeper.') == {'role': 'GK'}
  assert match_chat.highlight_from_question('highlight goalie') == {'role': 'GK'}
  assert match_chat.highlight_from_question('highlight ref') == {'official': 'referee'}
  assert match_chat.highlight_from_question('highlight the referee') == {'official': 'referee'}
  assert match_chat.highlight_from_question('Highlight the fastest player.') == {'stat': 'fastest'}
  assert match_chat.highlight_from_question('Box the right centre backs.') == {
      'role': 'CB', 'team': 'right'}
  assert match_chat.highlight_from_question('Clear the boxes.') == {'clear': True}
  assert match_chat.highlight_from_question('unhighlight all players') == {'clear': True}
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer('unhighlight all players', {'roster': [player()], 'log': []})
  assert text == 'Boxes cleared.'
  assert marks == []
  assert match_chat.highlight_from_question('Highlight the right back.') == {'role': 'RB'}


def test_highlight_line_is_not_shown_as_the_answer():
  spoken, spec = match_chat.extract_highlight('ARS 9 shot.')
  assert spoken == 'ARS 9 shot.'
  assert spec is None
  spoken, spec = match_chat.extract_highlight('HIGHLIGHT {"role": "GK"}')
  assert spoken == ''
  assert spec == {'role': 'GK'}
  spoken, spec = match_chat.extract_highlight('{"team": "right", "role": "CB"}')
  assert spec['team'] == 'right' and spec['role'] == 'CB'
  spoken, spec = match_chat.extract_highlight('Boxes off.\nHIGHLIGHT {"clear": true}')
  assert spoken == 'Boxes off.'
  assert spec == {'clear': True}


def test_camera_requests():
  roster = [
      player(player=6, name='Saka', shirt=7, role='RM'),
      player(team=1, player=6, name='Foden', shirt=7, role='RM', x=10),
      player(player=8, name='Jesus', shirt=9, role='CF'),
      player(player=0, name='Ramsdale', shirt=1, role='GK'),
      player(team=1, player=0, name='Ederson', shirt=31, role='GK', x=10),
  ]
  snap = {
      'left_name': 'FRQ',
      'right_name': 'RBA',
      'roster': roster,
      'log': [],
      'ball': [0, 0],
  }
  assert match_chat.camera_from_question('Who scored?') is None
  assert match_chat.camera_from_question('Highlight number 7', snap) is None
  assert match_chat.camera_from_question('show me the goalkeeper', snap) is None
  text, camera = match_chat.camera_from_question("show me 7's perspective", snap)
  assert camera is None
  assert 'Saka' in text and 'Foden' in text
  text, camera = match_chat.camera_from_question(
      "show me Schmarsenal 7's perspective", snap)
  assert camera == {'team': 0, 'player': 6, 'lens': 0}
  assert text == 'First person, ARS Saka 7.'
  text, camera = match_chat.camera_from_question('follow 7', snap)
  assert camera is None
  text, camera = match_chat.camera_from_question('follow schman city 7', snap)
  assert camera == {'team': 1, 'player': 6, 'lens': 1}
  assert text == 'Following MNC Foden 7.'
  text, camera = match_chat.camera_from_question('can you follow Saka', snap)
  assert camera == {'team': 0, 'player': 6, 'lens': 1}
  text, camera = match_chat.camera_from_question("through Jesus's eyes", snap)
  assert camera == {'team': 0, 'player': 8, 'lens': 0}
  text, camera = match_chat.camera_from_question('first person on the left 9', snap)
  assert camera == {'team': 0, 'player': 8, 'lens': 0}
  text, camera = match_chat.camera_from_question(
      'track number seven on the right', snap)
  assert camera == {'team': 1, 'player': 6, 'lens': 1}
  text, camera = match_chat.camera_from_question(
      'follow the schmarsenal striker', snap)
  assert camera == {'team': 0, 'player': 8, 'lens': 1}
  text, camera = match_chat.camera_from_question('action camera on 7', snap)
  assert camera is None and 'Say which one.' in text
  text, camera = match_chat.camera_from_question('follow the ball', snap)
  assert camera == {'team': -1, 'player': 0, 'lens': 2}
  text, camera = match_chat.camera_from_question('action camera', snap)
  assert text == 'Action camera.'
  text, camera = match_chat.camera_from_question('back to broadcast', snap)
  assert camera == {'team': -1, 'player': 0, 'lens': 0}
  text, camera = match_chat.camera_from_question('free look', snap)
  assert camera == {'team': -1, 'player': 0, 'lens': 3}
  text, camera = match_chat.camera_from_question('switch the camera', snap)
  assert text == 'Say which camera.' and camera is None
  text, camera = match_chat.camera_from_question('follow shirt 44', snap)
  assert text == 'No player in the match matches that.' and camera is None
  dribble = {
      'left_name': 'FRQ',
      'right_name': 'RBA',
      'roster': [
          player(player=1, name='Quiet', shirt=4),
          player(player=8, name='Dribbler', shirt=8, role='CM'),
      ],
      'log': _passes(0, 8, 'CONTROL', 4) + _passes(0, 4, 'CONTROL', 1),
      'ball': [0, 0],
  }
  text, camera = match_chat.camera_from_question(
      'follow the player with the most dribbles', dribble)
  assert camera == {'team': 0, 'player': 8, 'lens': 1}
  assert 'Dribbler' in text
  text, marks, camera, _hidden, _captions, _lines = match_chat.answer("show me Saka's view", snap)
  assert marks is None
  assert camera == {'team': 0, 'player': 6, 'lens': 0}
  text, marks, camera, _hidden, _captions, _lines = match_chat.answer('highlight the goalkeeper', snap)
  assert camera is None
  assert len(marks) == 2
  assert 'Boxed' in text
  text, marks, camera, _hidden, _captions, _lines = match_chat.answer('highlight goalie', snap)
  assert camera is None
  assert len(marks) == 2
  text, marks, camera, _hidden, _captions, _lines = match_chat.answer('highlight ref', snap)
  assert camera is None
  assert text == 'Boxed the referee.'
  assert marks == [{'team': -1, 'player': 0}]


def test_closed_model_is_a_plain_error():
  try:
    match_chat.answer('Who scored?', {'score': [0, 0], 'log': []},
                      url='http://127.0.0.1:9/api/chat', timeout=1)
  except match_chat.MatchChatError as error:
    assert 'not running' in str(error)
  else:
    raise AssertionError('a closed port should fail')


def test_hide_and_show():
  roster = [
      player(player=0, name='Raya', shirt=1, role='GK'),
      player(player=1, name='Gabriel', shirt=5, role='CB'),
      player(player=2, name='Timber', shirt=3, role='LB'),
      player(player=3, name='White', shirt=2, role='RB'),
      player(player=4, name='Saka', shirt=7, role='RM', x=-8, y=20),
      player(player=5, name='Odegaard', shirt=8, role='CM'),
      player(team=1, player=0, name='Ederson', shirt=1, role='GK', x=40),
      player(team=1, player=4, name='Foden', shirt=7, role='AM', x=20, y=8),
      player(team=1, player=2, name='Dias', shirt=4, role='CB', x=30),
      player(team=1, player=9, name='Haaland', shirt=9, role='CF', x=15),
  ]
  snap = {'roster': roster, 'log': [], 'left_name': 'ARS', 'right_name': 'MNC'}
  text, marks, camera, hidden, _captions, _lines = match_chat.answer('hide the ball', snap)
  assert marks is None and camera is None
  assert text == 'Hid the ball.'
  assert hidden == {'players': [], 'ball': True}
  text, _marks, _camera, hidden, _captions, _lines = match_chat.answer('hide the ref', snap)
  assert text == 'Hid the referee.'
  assert hidden['players'] == [{'team': -1, 'player': 0}]
  assert hidden['ball'] is False
  text, _marks, _camera, hidden, _captions, _lines = match_chat.answer('hide the 7s for both sides', snap)
  assert { (row['team'], row['player']) for row in hidden['players'] } == {(0, 4), (1, 4)}
  assert 'Saka' in text and 'Foden' in text
  text, _marks, _camera, hidden, _captions, _lines = match_chat.answer(
      'hide the defenders for schmarsenal', snap)
  assert {row['player'] for row in hidden['players']} == {1, 2, 3}
  assert all(row['team'] == 0 for row in hidden['players'])
  text, _marks, _camera, hidden, _captions, _lines = match_chat.answer('hide all odd numbers', snap)
  odd = {row['shirt'] for row in roster if row['shirt'] % 2}
  hidden_shirts = {
      (row['team'], row['player']) for row in hidden['players']}
  assert hidden_shirts == {
      (row['team'], row['player']) for row in roster if row['shirt'] in odd}
  kept = hidden
  text, _marks, _camera, shown, _captions, _lines = match_chat.answer(
      'show all odd numbers', dict(snap, hidden=kept))
  assert shown == {'players': [], 'ball': False}
  assert text.startswith('Showing')
  text, _marks, _camera, hidden, _captions, _lines = match_chat.answer('hide the goalie', snap)
  assert {(row['team'], row['player']) for row in hidden['players']} == {(0, 0), (1, 0)}
  text, marks, camera, hidden, _captions, _lines = match_chat.answer('show me the goalkeeper', snap)
  assert hidden is None and camera is None and len(marks) == 2
  text, marks, camera, hidden, captions, _lines = match_chat.answer("show me Saka's view", snap)
  assert hidden is None and camera['lens'] == 0 and marks is None and captions is None


def test_captions():
  text, marks, camera, hidden, captions, _lines = match_chat.answer('turn off captions', {})
  assert text == 'Captions off.'
  assert captions is False
  assert marks is None and camera is None and hidden is None
  text, _marks, _camera, _hidden, captions, _lines = match_chat.answer(
      'turn on the head labels', {'captions': False})
  assert text == 'Captions on.'
  assert captions is True
  text, _marks, _camera, _hidden, captions, _lines = match_chat.answer(
      'hide captions', {'captions': True})
  assert captions is False
  text, _marks, _camera, _hidden, captions, _lines = match_chat.answer(
      'toggle captions', {'captions': False})
  assert captions is True
  text, _marks, _camera, hidden, captions, _lines = match_chat.answer('hide the ball', {})
  assert captions is None and hidden['ball'] is True


def _ends(lines):
  return {(
      (row['a']['team'], row['a']['player']),
      (row['b']['team'], row['b']['player']),
  ) for row in lines}


def _touch(team, shirt, action, clock, name=''):
  return {
      'team': team, 'shirt': shirt, 'name': name,
      'action': action, 'clock': clock,
  }


def _completed(team, shirt, clock, mate_team, mate_shirt, mate_clock):
  return [
      _touch(team, shirt, 'SHORT PASS', clock),
      _touch(mate_team, mate_shirt, 'CONTROL', mate_clock),
  ]


def test_top_few_present_and_future():
  roster = [
      player(player=1, name='Archimedes', shirt=4, team=1, role='CB', x=20),
      player(player=2, name='One', shirt=8, role='CM'),
      player(player=3, name='Two', shirt=10, role='CF', x=8),
      player(player=4, name='Three', shirt=6, role='CM', x=-8),
      player(player=5, name='Four', shirt=11, role='LM', y=20),
  ]
  log = (_passes(1, 4, 'SHORT PASS', 2, '20:00')
         + _passes(0, 8, 'SHORT PASS', 5, '21:00')
         + _passes(0, 10, 'LONG PASS', 4, '22:00')
         + _passes(0, 6, 'HIGH PASS', 3, '23:00')
         + _passes(0, 11, 'SHORT PASS', 1, '24:00'))
  snap = {
      'left_name': 'FRQ', 'right_name': 'RBA', 'score': [0, 0],
      'clock': '32:19', 'roster': roster, 'log': log, 'future': log,
      'lines': [],
  }
  text, marks, _camera, _hidden, _captions, lines = match_chat.answer(
      'highlight the 3 players with most passes', snap)
  assert [mark['player'] for mark in marks] == [2, 3, 4]
  assert 'One' in text and 'Two' in text and 'Three' in text
  assert 'Archimedes' not in text
  assert lines is None
  text, marks, _camera, _hidden, _captions, lines = match_chat.answer(
      'connect the 3 players who will have the most passes', snap)
  assert marks is None
  assert 'One' in text and 'Two' in text and 'Three' in text
  ends = sorted((row['a']['player'], row['b']['player']) for row in lines)
  assert ends == [(2, 3), (2, 4), (3, 4)]


def test_key_moments():
  rows = [
      _touch(1, 7, 'SHORT PASS', '12:01', 'Saka'),
      _touch(0, 9, 'CONTROL', '12:08', 'Haaland'),
      _touch(0, 9, 'SHOT', '12:10', 'Haaland'),
      _touch(0, 9, 'GOAL', '12:11', 'Haaland'),
      _touch(0, 4, 'LONG PASS', '40:00', 'Dias'),
      _touch(1, 3, 'OWN GOAL', '40:20', 'Silva'),
  ]
  snap = {'log': [], 'future': rows, 'roster': []}
  text, segments = match_chat.key_moments_from_question('highlight key moments', snap)
  assert text == '2 key moments.'
  assert [(row['start'], row['end']) for row in segments] == [
      (11 * 60 + 11, 12 * 60 + 11),
      (39 * 60 + 20, 40 * 60 + 20),
  ]
  assert segments[0]['start_clock'] == '11:11'
  reply, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'highlight key moments', snap)
  assert reply == '2 key moments.'
  assert marks is None
  assert match_chat.key_moments_from_question('highlight the striker', snap) is None
  shown, shown_rows = match_chat.key_moments_from_question('show key moments', snap)
  assert shown == '2 key moments.'
  assert shown_rows == segments
  found, found_rows = match_chat.key_moments_from_question('find key moments', snap)
  assert found == '2 key moments.'
  assert found_rows == segments
  cleared, empty = match_chat.key_moments_from_question('unhighlight key moments', snap)
  assert cleared == 'Key moments cleared.'
  assert empty == []
  hidden, hidden_rows = match_chat.key_moments_from_question('hide key moments', snap)
  assert hidden == 'Key moments cleared.' and hidden_rows == []
  removed, removed_rows = match_chat.key_moments_from_question('remove key moments', snap)
  assert removed == 'Key moments cleared.' and removed_rows == []
  alone = [_touch(0, 9, 'SHOT', '1:00'), _touch(0, 9, 'GOAL', '1:02')]
  early, early_rows = match_chat.key_moments_from_question(
      'highlight key moments', {'future': alone})
  assert early == 'Key moment, 0:02 to 1:02.'
  assert [(row['start'], row['end']) for row in early_rows] == [(2, 62)]
  quiet, gone = match_chat.key_moments_from_question(
      'highlight key moments', {'log': [], 'future': []})
  assert quiet == 'No goal on this timeline.'
  assert gone == []


def test_future_wording():
  roster = [
      player(player=1, name='Lovelace', shirt=1, role='GK'),
      player(player=9, name='Curie', shirt=9, role='CF', x=10),
  ]
  future = [_touch(0, 9, 'GOAL', '47:15', 'Curie')]
  future += _completed(0, 9, '12:00', 0, 1, '12:01')
  future += _completed(0, 9, '13:00', 0, 1, '13:01')
  snap = {
      'left_name': 'FRQ', 'right_name': 'RBA', 'score': [1, 0],
      'clock': '03:13', 'roster': roster, 'log': [], 'future': future,
  }
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'highlight the player who will score a goal', snap)
  assert text == 'Boxed ARS Curie 9, 1 goal.'
  assert marks == [{'team': 0, 'player': 9}]
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'highlight the player who will have the most short passes', snap)
  assert text == 'Boxed ARS Curie 9, 2 short passes.'
  assert marks == [{'team': 0, 'player': 9}]
  empty = dict(snap)
  empty['future'] = [_touch(0, 9, 'GOAL', '47:15', 'Curie')]
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'highlight the player who will have the most short passes', empty)
  assert text == 'No player in the match matches that.'
  assert marks == []


def test_future_match():
  roster = [
      player(player=0, name='Silva', shirt=4, role='CB'),
      player(player=1, name='Stones', shirt=5, role='CB', x=-18),
      player(team=1, player=2, name='Dias', shirt=3, role='CB', x=20),
      player(team=1, player=3, name='Akanji', shirt=6, role='CB', x=18),
      player(player=9, name='Haaland', shirt=9, role='CF', x=10),
  ]
  future = []
  future += _completed(0, 4, '10:00', 0, 5, '10:01')
  future += _completed(0, 4, '12:00', 0, 5, '12:01')
  future += _completed(0, 4, '14:00', 0, 5, '14:01')
  future += _completed(0, 5, '20:00', 0, 4, '20:01')
  future += _completed(1, 6, '22:00', 1, 3, '22:01')
  future += _completed(1, 6, '45:30', 1, 3, '45:30')
  future += _completed(1, 3, '50:00', 1, 6, '50:01')
  future += _completed(1, 3, '51:00', 1, 6, '51:01')
  future += _completed(1, 3, '52:00', 1, 6, '52:01')
  future += _completed(1, 3, '53:00', 1, 6, '53:01')
  future += _completed(1, 3, '54:00', 1, 6, '54:01')
  future += [
      _touch(0, 9, 'GOAL', '30:00', 'Haaland'),
      _touch(0, 9, 'GOAL', '70:00', 'Haaland'),
      _touch(1, 3, 'GOAL', '60:00', 'Dias'),
      _touch(0, 4, 'OWN GOAL', '40:00', 'Silva'),
      _touch(0, 4, 'SHOT', '08:00'),
      _touch(0, 9, 'SHOT', '31:00'),
      _touch(0, 9, 'SHOT', '32:00'),
      _touch(0, 9, 'SHOT', '33:00'),
  ]
  snap = {
      'left_name': 'FRQ', 'right_name': 'RBA', 'score': [0, 0],
      'clock': '05:00', 'roster': roster, 'log': [], 'future': future,
      'lines': [],
  }
  text, marks, _camera, _hidden, _captions, lines = match_chat.answer(
      'highlight the player who will score the most goals', snap)
  assert text == 'Boxed ARS Haaland 9, 2 goals.'
  assert marks == [{'team': 0, 'player': 9}]
  assert lines is None
  text, marks, _camera, _hidden, _captions, lines = match_chat.answer(
      'connect the 3 cbs from either team who will by 45:30 have completed the most passes',
      snap)
  assert text == (
      'Connected ARS Silva 4, 3 completed passes, '
      'MNC Akanji 6, 2 completed passes, and '
      'ARS Stones 5, 1 completed pass by 45:30.')
  assert marks is None
  ends = sorted((row['a']['player'], row['b']['player']) for row in lines)
  assert ends == [(0, 1), (0, 3), (1, 3)]
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'who will score the most goals?', snap)
  assert text == 'ARS Haaland 9, 2 goals.'
  assert marks is None
  bare = dict(snap)
  bare['future'] = None
  text, marks, _camera, _hidden, _captions, lines = match_chat.answer(
      'highlight the player who will score the most goals', bare)
  assert text == 'This match has no saved touch list.'
  assert marks is None
  assert lines is None
  live = [_touch(0, 4, 'SHOT', '04:00')] * 4
  snap['log'] = live
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'highlight the player with the most shots', snap)
  assert marks == [{'team': 0, 'player': 0}]
  text, marks, _camera, _hidden, _captions, _lines = match_chat.answer(
      'highlight the player who will have the most shots', snap)
  assert text == 'Boxed ARS Haaland 9, 3 shots.'
  assert marks == [{'team': 0, 'player': 9}]


def test_lines():
  roster = [
      player(player=0, name='Raya', shirt=1, role='GK'),
      player(player=1, name='Gabriel', shirt=5, role='CB'),
      player(player=2, name='Saliba', shirt=4, role='CB', y=4),
      player(player=5, name='Rice', shirt=41, role='CM', x=-6),
      player(player=6, name='Odegaard', shirt=8, role='CM', x=-4, y=2),
      player(player=7, name='Partey', shirt=6, role='CM', x=-4, y=-2),
      player(player=8, name='Saka', shirt=7, role='RM', y=20),
      player(team=1, player=2, name='Dias', shirt=5, role='CB', x=30),
      player(team=1, player=3, name='Stones', shirt=6, role='CB', x=30, y=4),
      player(team=1, player=6, name='Foden', shirt=7, role='AM', x=20),
      player(team=1, player=8, name='Kdb', shirt=17, role='CM', x=10),
      player(team=1, player=9, name='Bernardo', shirt=20, role='CM', x=12),
      player(team=1, player=10, name='Rodri', shirt=16, role='CM', x=8),
  ]
  snap = {'roster': roster, 'log': [], 'left_name': 'FRQ', 'right_name': 'RBA'}
  text, _marks, _camera, _hidden, _captions, lines = match_chat.answer(
      'connect the midfielders for ARS', snap)
  assert text == 'Connected 3 players.'
  assert _ends(lines) == {((0, 5), (0, 6)), ((0, 5), (0, 7)), ((0, 6), (0, 7))}
  text, _marks, _camera, _hidden, _captions, more = match_chat.answer(
      'connect the centerbacks for MNC', dict(snap, lines=lines))
  assert text == 'Connected MNC Dias 5 and MNC Stones 6.'
  assert ((1, 2), (1, 3)) in _ends(more)
  assert len(more) == 4
  text, _marks, _camera, _hidden, _captions, both = match_chat.answer(
      "connect the 7's from both teams", snap)
  assert text == 'Connected ARS Saka 7 and MNC Foden 7.'
  assert _ends(both) == {((0, 8), (1, 6))}
  text, _marks, _camera, _hidden, _captions, across = match_chat.answer(
      'connect schmarsenal 7 to all schman city midfielders', snap)
  assert text == 'Connected ARS Saka 7 to MNC Kdb 17, MNC Bernardo 20, and MNC Rodri 16.'
  assert _ends(across) == {((0, 8), (1, 8)), ((0, 8), (1, 9)), ((0, 8), (1, 10))}
  text, _marks, _camera, _hidden, _captions, kept = match_chat.answer(
      'disconnect the centerbacks', dict(snap, lines=more))
  assert text.startswith('Disconnected')
  assert ((1, 2), (1, 3)) not in _ends(kept)
  assert len(kept) == 3
  text, _marks, _camera, _hidden, _captions, cleared = match_chat.answer(
      'clear lines', dict(snap, lines=kept))
  assert text == 'Lines cleared.'
  assert cleared == []
  text, _marks, _camera, _hidden, _captions, cleared = match_chat.answer(
      'clear connections', dict(snap, lines=kept))
  assert text == 'Connections cleared.'
  assert cleared == []
  text, _marks, _camera, _hidden, _captions, same = match_chat.answer(
      'connect the goalkeeper for ARS', snap)
  assert text == 'Say another player to connect.'
  assert same is None
  text, _marks, _camera, _hidden, _captions, lines = match_chat.answer(
      'hide the ball', snap)
  assert lines is None


if __name__ == '__main__':
  test_role_and_team()
  test_fastest_on_a_side()
  test_zones_and_ball()
  test_inactive_and_empty_are_not_boxed()
  test_shirt_and_name()
  test_snapshot_uses_the_log_and_the_scoreboard_names()
  test_record_counts_the_whole_log()
  test_odd_shirts_and_pass_counts()
  test_most_dribbles()
  test_long_passed_and_everyone()
  test_fullbacks_are_not_the_whole_side()
  test_club_names_pick_a_side()
  test_question_picks_the_boxes()
  test_highlight_line_is_not_shown_as_the_answer()
  test_camera_requests()
  test_hide_and_show()
  test_captions()
  test_lines()
  test_top_few_present_and_future()
  test_key_moments()
  test_future_wording()
  test_future_match()
  test_closed_model_is_a_plain_error()
  print('match chat ok')
