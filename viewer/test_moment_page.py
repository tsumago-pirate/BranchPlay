"""The key-moment article: the stretch log, the picture, and one paragraph."""

import asyncio
import inspect
import os
import tempfile

import numpy as np
from PIL import Image

import languages
import match_chat
import moment_page
import saves
import watch

ROWS = [
    {
        'team': 0, 'shirt': 7, 'name': 'Saka', 'action': 'CONTROL',
        'clock': '11:00', 'x': 10.0, 'y': -4.0, 'speed': 4.2,
        'ball_x': 10.1, 'ball_y': -4.1, 'ball_speed': 8.0,
    },
    {
        'team': 0, 'shirt': 7, 'name': 'Saka', 'action': 'SHOT',
        'clock': '12:08', 'x': 22.0, 'y': -2.0, 'speed': 6.1,
        'ball_x': 24.0, 'ball_y': -1.0, 'ball_speed': 16.4,
    },
    {
        'team': 0, 'shirt': 7, 'name': 'Saka', 'action': 'GOAL',
        'clock': '12:11', 'x': 40.0, 'y': 0.0, 'speed': 5.0,
        'ball_x': 41.0, 'ball_y': 0.2, 'ball_speed': 12.0,
    },
    {
        'team': 1, 'shirt': 4, 'name': 'Dias', 'action': 'CONTROL',
        'clock': '13:00', 'x': 0.0, 'y': 0.0, 'speed': 1.0,
        'ball_x': 0.0, 'ball_y': 0.0, 'ball_speed': 1.0,
    },
]

START = 11 * 60 + 11
END = 12 * 60 + 11

stretch = moment_page.segment_rows(ROWS, START, END)
assert [row['clock'] for row in stretch] == ['12:08', '12:11']
assert moment_page.segment_rows(ROWS, 'nope', END) == []

log = moment_page.read_segment_actions(stretch, 'FRQ', 'RBA')
assert 'ARS' in log
assert 'Saka, shirt 7, shot' in log
assert 'On this shot, Saka was at 22.0, -2.0 and moving 6.1 m/s' in log
assert 'On this shot, the ball was at 24.0, -1.0 and moving 16.4 m/s' in log
assert 'goal' in log
assert 'The only actions are: shot, goal.' in log
assert 'Dias' not in log
assert '11:00' not in log

assert moment_page.heading(stretch, 'FRQ', 'RBA') == "Saka's goal"
assert moment_page.heading(stretch, 'FRQ', 'RBA', 'es') == 'Gol de Saka'
assert moment_page.heading(stretch, 'FRQ', 'RBA', 'de') == 'Tor von Saka'
assert moment_page.writing_instructions('en') == moment_page.INSTRUCTIONS
assert 'Spanish' in moment_page.writing_instructions('es')
assert languages.normalize('fr') == 'fr'
assert languages.normalize('nope') == 'en'
assert languages.phrase('pt', 'what_if') == 'E SE'
assert moment_page.heading([
    {'team': 1, 'shirt': 5, 'name': 'Gabriel', 'action': 'OWN GOAL', 'clock': '40:00'},
], 'ARS', 'MNC') == 'Own goal, Gabriel'
assert moment_page.heading([
    {'action': 'SHOT', 'name': 'Saka'},
], 'ARS', 'MNC') == 'Key moment'
assert moment_page.span_label(START, END) == '11:11–12:11'

assert moment_page.one_paragraph('One. Two. Three. Four. Five.') == 'One. Two. Three.'
assert moment_page.one_paragraph('Line one.\n\nLine two.') == 'Line one. Line two.'
assert moment_page.one_paragraph('  "Kept."  ') == 'Kept.'
assert moment_page.one_paragraph('   ') == ''

assert moment_page.explain([], 'FRQ', 'RBA') == moment_page.EMPTY
assert moment_page.invented_actions('He passed it.', stretch) == ['pass']
assert moment_page.invented_actions('Saka shot and scored a goal.', stretch) == []


class Sink(object):
  def __init__(self):
    self.got = []

  def extend_messages(self, source, messages):
    self.got.extend(messages)


sink = Sink()
provider = moment_page.SegmentLog(log)
asyncio.run(provider.before_run(agent=None, session=None, context=sink, state={}))
assert sink.got[0].text == log
assert 'shirt 7' in sink.got[0].text

frames = []
for index in range(8):
  frame = np.zeros((32, 48, 3), dtype=np.uint8)
  frame[:, :, 1] = 20 * index
  frames.append(frame)
picked = moment_page.sample_frames(frames, 4)
assert len(picked) == 4
assert int(picked[0][0, 0, 1]) == 0
assert int(picked[-1][0, 0, 1]) == 20 * 7

folder = tempfile.mkdtemp(prefix='branchplay-page-')
path = os.path.join(folder, 'stretch.webp')
moment_page.write_preview(path, frames)
with Image.open(path) as image:
  assert image.format == 'WEBP'
  assert image.n_frames == 8
  assert image.size == moment_page.PREVIEW_SIZE
assert os.path.getsize(path) > 64
assert watch._clip_media_type(path) == 'image/webp'
assert watch._clip_media_type('/tmp/clip.mp4') == 'video/mp4'

live = watch.LiveMatch()
live.request_brief(START, END, 4)
taken = live.take_brief()
assert taken[0] == START and taken[1] == END
view = live.brief_view()
assert view['id'] == 4
assert view['phase'] == 'writing'
assert view['span'] == '11:11–12:11'
assert live.brief_active(taken[2])
live.set_brief(title="Saka's goal", lead='Saka scored.', phase='ready', progress=1)
assert live.brief_view()['title'] == "Saka's goal"
assert live.brief_view()['lead'] == 'Saka scored.'
live.request_moment(START, END, 9)
assert live.brief_view() is None
assert not live.brief_active(taken[2])
moment = live.take_moment()
assert moment[0] == START and moment[1] == END

live.request_brief(1, 2, 1)
live.request_brief_stop()
live.set_brief(lead='late')
assert live.take_brief() is None
assert live.brief_view() is None

live.set_sim('sim-lines')
live.set_branches([{'id': '7', 'parent': '', 'clock': 10, 'end_clock': 80}])
assert live.set_line('7')
captured = {}


def _capture_moments(sim_id, rows, folder=None):
  captured['id'] = sim_id
  captured['rows'] = rows


original_write = saves.write_moments
saves.write_moments = _capture_moments
try:
  live._answer('highlight key moments', 3, {
      'future': [{
          'team': 0, 'shirt': 9, 'name': 'Haaland', 'action': 'GOAL',
          'clock': '1:02', 'x': 0, 'y': 0, 'speed': 1,
          'ball_x': 0, 'ball_y': 0, 'ball_speed': 1,
      }],
  }, [])
  assert captured['id'] == 'sim-lines'
  assert list(captured['rows']) == ['7']
  assert captured['rows']['7'] == [{'start': 2, 'end': 62}]
  assert live.moments() == [{'start': 2, 'end': 62}]
  assert live.set_line('')
  assert live.moments() == []
  live._answer('highlight key moments', 5, {
      'future': [{
          'team': 0, 'shirt': 9, 'name': 'Haaland', 'action': 'GOAL',
          'clock': '2:00', 'x': 0, 'y': 0, 'speed': 1,
          'ball_x': 0, 'ball_y': 0, 'ball_speed': 1,
      }],
  }, [])
  assert captured['rows'][''] == [{'start': 60, 'end': 120}]
  assert captured['rows']['7'] == [{'start': 2, 'end': 62}]
  assert live.moments() == [{'start': 60, 'end': 120}]
  live._answer('hide key moments', 6, {'future': []}, [])
  assert '' not in captured['rows']
  assert captured['rows']['7'] == [{'start': 2, 'end': 62}]
  assert live.set_line('7')
  assert live.moments() == [{'start': 2, 'end': 62}]
  live._answer('hide key moments', 4, {'future': []}, [])
  assert captured['rows'] == {}
  assert live.moments() == []
finally:
  saves.write_moments = original_write

assert 'agent_framework' not in inspect.getsource(match_chat)
text, marks, camera, hidden, captions, lines = match_chat.answer(
    'hide key moments', {})
assert text == 'Key moments cleared.'
assert marks is None and camera is None and hidden is None
assert captions is None and lines is None

paragraph = moment_page.explain(stretch, 'FRQ', 'RBA')
folded = paragraph.lower()
assert 'saka' in folded
assert 'dias' not in folded
assert 'function' not in folded
assert moment_page.invented_actions(paragraph, stretch) == []
assert '\n' not in paragraph
assert paragraph == moment_page.one_paragraph(paragraph)
assert len(paragraph.split()) <= 160
print('moment page ok')
print(paragraph)
