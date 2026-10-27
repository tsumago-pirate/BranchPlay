"""The key-moment article.

The match chat is unchanged. This page asks Phi-4 mini, through Microsoft
Agent Framework, for one short paragraph about one stretch of the touch log.
Phi-4 mini does not emit tool calls, and offering it a tool makes it refuse.
A context provider supplies the same reader the tool would have called, so
the paragraph is grounded in this stretch: names, shirts, actions, places,
and speeds.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import asyncio
import os
import re

import cv2
import numpy as np
from PIL import Image

import languages
import match_chat
import saves
from agent_framework import Agent
from agent_framework import ChatOptions
from agent_framework import ContextProvider
from agent_framework import Message
from agent_framework.ollama import OllamaChatClient

# The same local Phi-4 the match chat uses. This page does not call
# match_chat.answer.
MODEL = 'phi4-mini'
OLLAMA_HOST = 'http://127.0.0.1:11434'

# A little looping picture, not the broadcast clip.
PREVIEW_SIZE = (384, 216)
PREVIEW_FRAMES = 36
PREVIEW_MS = 120

EMPTY = 'No action in this stretch is in the log.'
UNANSWERED = 'Phi-4 did not answer.'

INSTRUCTIONS = (
    'You write one short paragraph for a match report. '
    'Three sentences at most. '
    'Say why this moment mattered and what the logged actions show allowed it. '
    'Use the player names and shirt numbers from the action log. '
    'The only actions you may name are the ones listed as the only actions. '
    'Each line says which action its speeds belong to. '
    'Use a speed only for the action named on that same line. '
    'Do not invent a player or a number that is not in the log. '
    'Do not mention the score, a lead, or any result the lines do not state. '
    'Do not add praise the log does not support. '
    'No title, no list, no heading.'
)


class MomentPageError(Exception):
  """Phi-4 did not return a paragraph."""


def clock_label(seconds):
  """A match clock as MM:SS."""
  try:
    seconds = int(seconds)
  except (TypeError, ValueError):
    seconds = 0
  if seconds < 0:
    seconds = 0
  return '%02d:%02d' % (seconds // 60, seconds % 60)


def span_label(start, end):
  return '%s–%s' % (clock_label(start), clock_label(end))


def segment_rows(rows, start, end):
  """Touches whose clock falls inside the stretch, inclusive."""
  try:
    start = int(start)
    end = int(end)
  except (TypeError, ValueError):
    return []
  chosen = []
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    clock = saves.clock_seconds(row.get('clock'))
    if clock < start or clock > end:
      continue
    chosen.append(row)
  return chosen


def _place(value):
  try:
    return '%.1f' % float(value)
  except (TypeError, ValueError):
    return '0.0'


def _side(row, left_name, right_name):
  try:
    team = int(row.get('team'))
  except (TypeError, ValueError):
    team = 0
  return left_name if team == 0 else right_name


def segment_text(rows, left_name, right_name):
  """One line per touch. Player speed and ball speed stay on that line."""
  left = match_chat.display_name(left_name, 'Left')
  right = match_chat.display_name(right_name, 'Right')
  lines = []
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    name = str(row.get('name') or '').strip()
    try:
      shirt = int(row.get('shirt'))
    except (TypeError, ValueError):
      shirt = 0
    who = '%s, shirt %s' % (name, shirt) if name else 'shirt %s' % shirt
    action = str(row.get('action') or '').strip().lower() or 'touch'
    clock = str(row.get('clock') or '').strip() or '00:00'
    lines.append(
        '%s %s %s, %s. On this %s, %s was at %s, %s and moving %s m/s. '
        'On this %s, the ball was at %s, %s and moving %s m/s.' % (
            clock,
            _side(row, left, right),
            who,
            action,
            action,
            name or who,
            _place(row.get('x')),
            _place(row.get('y')),
            _place(row.get('speed')),
            action,
            _place(row.get('ball_x')),
            _place(row.get('ball_y')),
            _place(row.get('ball_speed')),
        ))
  if len(lines) > 80:
    lines = lines[-80:]
    lines.insert(0, 'Earlier actions in this stretch are omitted. These are the latest.')
  return '\n'.join(lines)


def _action_names(rows):
  names = []
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    action = str(row.get('action') or '').strip().lower()
    if action and action not in names:
      names.append(action)
  return names


def read_segment_actions(rows, left_name, right_name):
  """The action log for this stretch. The page gives this to Phi-4."""
  text = segment_text(rows, left_name, right_name)
  if not text:
    return EMPTY
  actions = _action_names(rows)
  allowed = ', '.join(actions) if actions else 'none'
  return (
      'Actions in this moment, oldest first. '
      'The only actions are: %s. Do not mention any other action. '
      'Use only these lines. On a line, the speed after the player is the '
      'player, and the speed after the ball is the ball.\n%s' % (allowed, text))


# Words the paragraph must not introduce when that action is absent.
_ACTION_WORDS = (
    'pass', 'shot', 'goal', 'control', 'trap', 'header', 'deflect',
    'catch', 'cross', 'tackle', 'dribble', 'save',
)


def _mentions(text, word):
  return re.search(r'\b%s' % re.escape(word), text) is not None


def invented_actions(paragraph, rows):
  """Action words in the paragraph that this stretch did not log."""
  text = str(paragraph or '').lower()
  allowed = ' '.join(_action_names(rows))
  found = []
  for word in _ACTION_WORDS:
    if _mentions(text, word) and not _mentions(allowed, word):
      found.append(word)
  return found


def heading(rows, left_name, right_name, language='en'):
  """A title from the log. The model does not write this."""
  language = languages.normalize(language)
  goal = None
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    action = str(row.get('action') or '').lower()
    if 'goal' in action:
      goal = row
  if goal is None:
    return languages.phrase(language, 'key_moment')
  name = str(goal.get('name') or '').strip()
  action = str(goal.get('action') or '').lower()
  if 'own' in action:
    if name:
      return languages.phrase(language, 'own_goal_name') % name
    return languages.phrase(language, 'own_goal')
  if name:
    return languages.phrase(language, 'goal_name') % name
  side = _side(
      goal,
      match_chat.display_name(left_name, 'Left'),
      match_chat.display_name(right_name, 'Right'))
  return languages.phrase(language, 'goal_side') % side


def _sentences(text):
  found = []
  start = 0
  for index, char in enumerate(text):
    if char not in '.!?':
      continue
    if index + 1 < len(text) and not text[index + 1].isspace():
      continue
    piece = text[start:index + 1].strip()
    if piece:
      found.append(piece)
    start = index + 1
  tail = text[start:].strip()
  if tail:
    found.append(tail)
  return found


def one_paragraph(text):
  """The first paragraph, and at most three sentences."""
  raw = str(text or '').replace('*', '').replace('`', '').replace('\r', '\n')
  parts = [part.strip() for part in raw.split('\n') if part.strip()]
  if not parts:
    return ''
  body = ' '.join(' '.join(part.split()) for part in parts)
  if len(body) >= 2 and body[0] == body[-1] == '"':
    body = body[1:-1].strip()
  sentences = _sentences(body)
  if len(sentences) > 3:
    body = ' '.join(sentences[:3])
  return body.strip()


class SegmentLog(ContextProvider):
  """Puts this stretch's action log in front of Phi-4 before it writes."""

  def __init__(self, log):
    super(SegmentLog, self).__init__('segment-log')
    self._log = log

  async def before_run(self, *, agent, session, context, state):
    context.extend_messages(self, [Message('user', [self._log])])


async def _ask(log, question, language='en'):
  agent = Agent(
      client=OllamaChatClient(model=MODEL, host=OLLAMA_HOST),
      name='MomentPage',
      instructions=writing_instructions(language),
      context_providers=[SegmentLog(log)],
  )
  result = await agent.run(
      question,
      options=ChatOptions(temperature=0, max_tokens=140),
  )
  return result.text


def writing_instructions(language='en'):
  """The page instructions. English stays the original text.

  Another language adds one sentence: write in that language, and keep
  the names from the log.
  """
  language = languages.normalize(language)
  if language == 'en':
    return INSTRUCTIONS
  return (
      INSTRUCTIONS +
      ' Write every sentence in %s. Keep player names as they are written in the log.'
      % languages.name(language))


def explain(rows, left_name, right_name, language='en'):
  """One short paragraph. Empty logs do not call the model.

  A paragraph that names an action this stretch did not log is rewritten once.
  """
  language = languages.normalize(language)
  log = read_segment_actions(rows, left_name, right_name)
  if log == EMPTY:
    return languages.phrase(language, 'empty')
  question = 'Explain this moment.'
  if language != 'en':
    question = 'Explain this moment in %s.' % languages.name(language)
  paragraph = ''
  for _ in range(2):
    try:
      text = asyncio.run(_ask(log, question, language))
    except Exception as error:
      raise MomentPageError(UNANSWERED) from error
    paragraph = one_paragraph(text)
    if not paragraph:
      raise MomentPageError(UNANSWERED)
    extra = invented_actions(paragraph, rows)
    if not extra:
      return paragraph
    question = (
        'Rewrite the paragraph. Do not mention %s. '
        'Name only the actions in the log, and keep each speed on its own line.'
        % ', '.join(extra))
    if language != 'en':
      question += ' Write every sentence in %s.' % languages.name(language)
  return paragraph


def sample_frames(frames, limit):
  """Evenly spaced frames, keeping the first and the last."""
  frames = list(frames or [])
  try:
    limit = int(limit)
  except (TypeError, ValueError):
    limit = 1
  if limit < 1 or len(frames) <= limit:
    return frames
  if limit == 1:
    return [frames[0]]
  last = len(frames) - 1
  chosen = []
  seen = set()
  for index in range(limit):
    pick = int(round(index * last / float(limit - 1)))
    if pick in seen:
      continue
    seen.add(pick)
    chosen.append(frames[pick])
  return chosen


def write_preview(path, frames):
  """A looping animated WebP. frames are BGR images."""
  images = []
  for frame in frames or []:
    array = np.asarray(frame)
    if array.ndim != 3 or array.shape[2] < 3:
      continue
    array = np.ascontiguousarray(array[:, :, :3])
    rgb = cv2.cvtColor(array, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, PREVIEW_SIZE, interpolation=cv2.INTER_AREA)
    images.append(Image.fromarray(rgb))
  if not images:
    raise MomentPageError('No picture for this moment.')
  folder = os.path.dirname(path)
  if folder:
    os.makedirs(folder, exist_ok=True)
  images[0].save(
      path,
      format='WEBP',
      save_all=True,
      append_images=images[1:],
      duration=PREVIEW_MS,
      loop=0,
      quality=40,
      method=4,
  )
  return path
