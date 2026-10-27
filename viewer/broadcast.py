"""Broadcast frame for a key-moment video.

This is the picture in the clip, not the match-window panels. The colors are
the flat bars in the palette: purple #38003C, green #00FF85, magenta #E90052,
cyan #04F5FF, and white.
"""

import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import languages

# Measured from the flat palette, not from a compressed photograph.
PURPLE = (0x38, 0x00, 0x3C)
GREEN = (0x00, 0xFF, 0x85)
MAGENTA = (0xE9, 0x00, 0x52)
CYAN = (0x04, 0xF5, 0xFF)
WHITE = (0xFF, 0xFF, 0xFF)

_BGR = {
    PURPLE: (0x3C, 0x00, 0x38),
    GREEN: (0x85, 0xFF, 0x00),
    MAGENTA: (0x52, 0x00, 0xE9),
    CYAN: (0xFF, 0xF5, 0x04),
    WHITE: (0xFF, 0xFF, 0xFF),
}

_SIDE = {'FRQ': 'ARS', 'RBA': 'MNC'}
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
_FONTS = {}
_FIELDS = {}
_CHEVRONS = {}

# How many video frames the bars take to finish extending.
SCORE_FRAMES = 22
LOWER_FRAMES = 28
# The opening title: arrive, hold full screen, then open onto the broadcast frame.
OPEN_IN = 18
OPEN_HOLD = 78
OPEN_OUT = 30
OPEN_FRAMES = OPEN_IN + OPEN_HOLD + OPEN_OUT
# The same card in reverse: the match closes, the title holds, then the type leaves.
CLOSE_IN = OPEN_OUT
CLOSE_HOLD = OPEN_HOLD
CLOSE_OUT = OPEN_IN
CLOSE_FRAMES = CLOSE_IN + CLOSE_HOLD + CLOSE_OUT

# The ribbon field, measured so the bars match the league pattern: a curve
# that flattens toward the bottom, with a stair along each edge, and wider
# bars in the foreground. These are plane units, not pixels.
_STEP = 0.11
_KICK = 0.026
_PERIOD = 0.18
_DUTY = 0.40


def goal_minute(seconds):
  """The match minute a clock is in. 86:52 is the 87th minute."""
  whole = max(0, int(seconds))
  return whole // 60 + 1


def side_label(name):
  """The short name drawn on the score bar."""
  text = str(name or '').strip().upper()
  if text in _SIDE:
    return _SIDE[text]
  letters = ''.join(ch for ch in text if ch.isalpha())
  if not letters:
    return '---'
  return letters[:3]


def scorer_card(rows, start, end):
  """The goal in this stretch: name, shirt, side, and minute."""
  start = int(start)
  end = int(end)
  found = None
  found_clock = end
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    action = str(row.get('action') or '').upper()
    if action not in ('GOAL', 'OWN GOAL'):
      continue
    try:
      clock = int(row.get('clock_seconds'))
    except (TypeError, ValueError):
      clock = None
    if clock is None:
      clock = _clock_seconds(row.get('clock'))
    if clock < start or clock > end:
      continue
    found = row
    found_clock = clock
  if found is None:
    return None
  try:
    shirt = int(found.get('shirt') or 0)
  except (TypeError, ValueError):
    shirt = 0
  try:
    team = int(found.get('team'))
  except (TypeError, ValueError):
    team = 0
  name = str(found.get('name') or '').strip()
  return {
      'name': name.upper() or 'GOAL',
      'shirt': shirt,
      'team': team,
      'minute': goal_minute(found_clock),
  }


def _clock_seconds(value):
  text = str(value or '0:0')
  parts = text.split(':')
  try:
    if len(parts) >= 2:
      return int(parts[0]) * 60 + int(parts[1])
    return int(float(text))
  except (TypeError, ValueError):
    return 0


def _ease(progress):
  progress = max(0.0, min(1.0, float(progress)))
  return 1.0 - (1.0 - progress) ** 3


def _font(weight, size):
  size = max(8, int(size))
  key = (weight, size)
  loaded = _FONTS.get(key)
  if loaded is not None:
    return loaded
  filename = 'Montserrat-ExtraBold.ttf' if weight == 'extra' else 'Montserrat-Bold.ttf'
  path = os.path.join(_FONT_DIR, filename)
  loaded = ImageFont.truetype(path, size)
  _FONTS[key] = loaded
  return loaded


def _field(width, height):
  """Plane coordinates for the ribbon pattern, cached per frame size.

  Dividing by depth makes the bars larger toward the bottom of the frame.
  The quadratic bends them so they flatten as they come forward, and the
  stair is applied later, one step at a time, so the edge can travel.
  """
  key = (int(width), int(height))
  found = _FIELDS.get(key)
  if found is not None:
    return found
  ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
  u = xs / float(max(1, width - 1))
  v = ys / float(max(1, height - 1))
  depth = 0.72 + 0.12 * u + 0.70 * v
  px = (u + 0.02) / depth
  py = (v + 0.04) / depth
  across = py - 0.55 * (px * px)
  along = px * 0.9 + py * 0.22
  if len(_FIELDS) > 2:
    _FIELDS.clear()
  _FIELDS[key] = (across, along)
  return across, along


def _chevron_field(width, height):
  """Right-pointing chevrons, one field for the full-screen title."""
  key = (int(width), int(height))
  found = _CHEVRONS.get(key)
  if found is not None:
    return found
  ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
  mid = (height - 1) * 0.5
  along = xs + np.abs(ys - mid) * 0.78
  if len(_CHEVRONS) > 2:
    _CHEVRONS.clear()
  _CHEVRONS[key] = along
  return along


def _ink(font, text):
  box = font.getbbox(text)
  return box[2] - box[0], box[3] - box[1], box[0], box[1]


def _write(draw, x, y, text, font, color):
  width, height, left, top = _ink(font, text)
  draw.text((x - left, y - top), text, font=font, fill=color)
  return width, height


class BroadcastPlate(object):
  """Paints the pattern, the score bar, and the scorer bar onto one frame."""

  def __init__(self, home, away, scorer, language='en'):
    self.home = side_label(home)
    self.away = side_label(away)
    self.scorer = scorer
    self.language = languages.normalize(language)
    self.clock = 0
    self.score = (0, 0)
    self.show_lower = False
    self.busy = True
    self._n = 0
    self._tick = 0
    self._open_i = 0
    self._close_i = None
    self._lower_i = None
    self._title_sprite = None
    self._title_key = None
    self._title_place = None
    self._card_buf = None
    self._score_sprite = None
    self._score_key = None
    self._lower_sprite = None
    self._lower_key = None
    self._pitch_key = None
    self._pitch_pic = None
    self._canvas_buf = None

  def set_state(self, clock, score, show_lower):
    self.clock = max(0, int(clock))
    self.score = (int(score[0]), int(score[1]))
    self.show_lower = bool(show_lower) and self.scorer is not None

  def begin_close(self):
    """The next stamps play the title again, in reverse."""
    self._close_i = 0

  def stamp(self, image):
    self._tick += 1
    if self._close_i is not None:
      index = self._close_i
      self._close_i += 1
      self.busy = True
      return self._closing(image, index)
    if self._open_i < OPEN_FRAMES:
      index = self._open_i
      self._open_i += 1
      self.busy = True
      return self._opening(image, index)
    index = self._n
    self._n += 1
    score_done = index + 1 >= SCORE_FRAMES
    score_p = 1.0 if score_done else _ease((index + 1) / float(SCORE_FRAMES))
    lower_p = 0.0
    lower_done = not self.show_lower
    if self.show_lower:
      if self._lower_i is None:
        self._lower_i = index
      gone = index - self._lower_i
      lower_done = gone + 1 >= LOWER_FRAMES
      lower_p = 1.0 if lower_done else _ease((gone + 1) / float(LOWER_FRAMES))
    self.busy = not (score_done and lower_done)
    return self._frame(image, score_p, lower_p)

  def _frame(self, image, score_p, lower_p):
    height, width = image.shape[:2]
    unit = height / 720.0
    margin = max(22, int(round(46 * unit)))
    inner_w = width - 2 * margin
    inner_h = height - 2 * margin
    if inner_w < 32 or inner_h < 32:
      return image
    scale = min(inner_w / float(width), inner_h / float(height))
    placed_w = max(2, int(round(width * scale)))
    placed_h = max(2, int(round(height * scale)))
    placed_w -= placed_w % 2
    placed_h -= placed_h % 2
    origin_x = (width - placed_w) // 2
    origin_y = (height - placed_h) // 2
    # The pitch covers the middle. The ribbon is only visible in the border,
    # so the rest of the frame is not rebuilt on every picture.
    canvas = self._canvas(width, height)
    self._border(canvas, origin_x, origin_y, origin_x + placed_w, origin_y + placed_h)
    # A hold stamps one picture many times. Resize it once.
    key = (id(image), width, height, placed_w, placed_h)
    cached = self._pitch_pic if self._pitch_key == key else None
    if cached is None:
      picture = image
      if placed_w != width or placed_h != height:
        picture = cv2.resize(image, (placed_w, placed_h), interpolation=cv2.INTER_LINEAR)
      self._pitch_key = key
      self._pitch_pic = picture
    else:
      picture = cached
    canvas[origin_y:origin_y + placed_h, origin_x:origin_x + placed_w] = picture
    inset = max(10, int(round(16 * unit)))
    score = self._score_bar(unit)
    self._extend(
        canvas, score, origin_x + inset, origin_y + inset, score_p, unit)
    if lower_p > 0 and self.scorer is not None:
      lower = self._lower_bar(unit, max(80, placed_w - 2 * inset))
      top = origin_y + placed_h - inset - lower.shape[0]
      self._extend(canvas, lower, origin_x + inset, top, lower_p, unit)
    return canvas

  def _opening(self, image, index):
    """A full-screen title, then it opens onto the broadcast frame."""
    height, width = image.shape[:2]
    card = self._card(width, height)
    self._chevrons(card)
    held = index < OPEN_IN + OPEN_HOLD
    if held:
      fade = 1.0 if index >= OPEN_IN else _ease((index + 1) / float(OPEN_IN))
      self._paint_title(card, fade)
      return card
    gone = index - (OPEN_IN + OPEN_HOLD)
    progress = _ease((gone + 1) / float(OPEN_OUT))
    template = self._frame(image, 0.0, 0.0)
    if progress >= 1.0:
      return template
    self._paint_title(card, max(0.0, 1.0 - progress * 1.6))
    # The match grows from the middle until the broadcast frame fills the picture.
    x0 = int(round((1.0 - progress) * width * 0.5))
    y0 = int(round((1.0 - progress) * height * 0.5))
    x1 = width - x0
    y1 = height - y0
    if x1 > x0 and y1 > y0:
      card[y0:y1, x0:x1] = template[y0:y1, x0:x1]
    return card

  def _closing(self, image, index):
    """The broadcast frame closes back onto the full-screen title."""
    height, width = image.shape[:2]
    card = self._card(width, height)
    self._chevrons(card)
    if index < CLOSE_IN:
      progress = _ease((index + 1) / float(CLOSE_IN))
      template = self._frame(image, 1.0, 1.0 if self.show_lower else 0.0)
      self._paint_title(card, min(1.0, progress * 1.6))
      remain = 1.0 - progress
      x0 = int(round((1.0 - remain) * width * 0.5))
      y0 = int(round((1.0 - remain) * height * 0.5))
      x1 = width - x0
      y1 = height - y0
      if x1 > x0 and y1 > y0:
        card[y0:y1, x0:x1] = template[y0:y1, x0:x1]
      return card
    if index < CLOSE_IN + CLOSE_HOLD:
      self._paint_title(card, 1.0)
      return card
    gone = index - (CLOSE_IN + CLOSE_HOLD)
    fade = 1.0 - _ease((gone + 1) / float(CLOSE_OUT))
    self._paint_title(card, fade)
    return card

  def _card(self, width, height):
    buf = self._card_buf
    if buf is None or buf.shape[0] != height or buf.shape[1] != width:
      buf = np.empty((height, width, 3), np.uint8)
      self._card_buf = buf
    return buf

  def _chevrons(self, canvas):
    """Magenta and purple chevrons, traveling to the right."""
    height, width = canvas.shape[:2]
    along = _chevron_field(width, height)
    period = max(96.0, height * 0.30)
    phase = self._tick * 4.0
    purple = np.mod(along - phase, period) < period * 0.42
    canvas[:] = _BGR[MAGENTA]
    canvas[purple] = _BGR[PURPLE]

  def _title_block(self, width, height):
    minute = None if self.scorer is None else int(self.scorer['minute'])
    key = (width, height, minute, self.language)
    if self._title_sprite is not None and self._title_key == key:
      return self._title_sprite, self._title_place
    word = languages.phrase(self.language, 'key_moment_card')
    word_size = max(48, int(round(height * 0.145)))
    word_font = _font('extra', word_size)
    word_w, word_h, _, _ = _ink(word_font, word)
    while word_w > width * 0.86 and word_size > 36:
      word_size -= 4
      word_font = _font('extra', word_size)
      word_w, word_h, _, _ = _ink(word_font, word)
    minute_text = '' if minute is None else "%d'" % minute
    minute_font = _font('extra', max(22, int(round(height * 0.055))))
    minute_w, minute_h = (0, 0)
    if minute_text:
      minute_w, minute_h, _, _ = _ink(minute_font, minute_text)
    bar_w = max(int(word_w * 0.28), 80)
    bar_h = max(6, int(round(height * 0.012)))
    gap = max(16, int(round(height * 0.028)))
    total_h = word_h + gap + bar_h
    if minute_text:
      total_h += gap + minute_h
    total_w = max(word_w, bar_w, minute_w)
    sprite = Image.new('RGBA', (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sprite)
    _write(draw, (total_w - word_w) // 2, 0, word, word_font, WHITE)
    bar_y = word_h + gap
    bar_x = (total_w - bar_w) // 2
    draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), fill=GREEN)
    if minute_text:
      _write(
          draw, (total_w - minute_w) // 2, bar_y + bar_h + gap,
          minute_text, minute_font, GREEN)
    raw = np.asarray(sprite)
    bgr = cv2.cvtColor(raw[:, :, :3], cv2.COLOR_RGB2BGR)
    alpha = raw[:, :, 3]
    place = ((width - total_w) // 2, (height - total_h) // 2)
    self._title_sprite = (bgr, alpha)
    self._title_key = key
    self._title_place = place
    return self._title_sprite, place

  def _paint_title(self, canvas, fade):
    if fade <= 0.0:
      return
    (bgr, alpha), (x, y) = self._title_block(canvas.shape[1], canvas.shape[0])
    x = int(x)
    y = int(y)
    row = min(bgr.shape[0], canvas.shape[0] - y)
    col = min(bgr.shape[1], canvas.shape[1] - x)
    if row <= 0 or col <= 0 or x < 0 or y < 0:
      return
    cover = alpha[:row, :col].astype(np.float32) * float(fade) / 255.0
    cover = cover[:, :, None]
    region = canvas[y:y + row, x:x + col]
    mixed = region.astype(np.float32) * (1.0 - cover) + bgr[:row, :col] * cover
    region[:] = mixed.astype(np.uint8)

  def _canvas(self, width, height):
    buf = self._canvas_buf
    if buf is None or buf.shape[0] != height or buf.shape[1] != width:
      buf = np.empty((height, width, 3), np.uint8)
      self._canvas_buf = buf
    return buf

  def _border(self, canvas, x0, y0, x1, y1):
    """Paint the moving ribbon only where the pitch does not cover it."""
    height, width = canvas.shape[:2]
    x0 = max(0, min(width, int(x0)))
    x1 = max(0, min(width, int(x1)))
    y0 = max(0, min(height, int(y0)))
    y1 = max(0, min(height, int(y1)))
    across, along = _field(width, height)
    along_phase = self._tick * (_STEP / 72.0)
    across_phase = self._tick * (_PERIOD / 300.0)
    magenta = _BGR[MAGENTA]
    purple = _BGR[PURPLE]
    strips = (
        (slice(0, y0), slice(0, width)),
        (slice(y1, height), slice(0, width)),
        (slice(y0, y1), slice(0, x0)),
        (slice(y0, y1), slice(x1, width)),
    )
    for rows, cols in strips:
      if rows.start >= rows.stop or cols.start >= cols.stop:
        continue
      stair = np.floor((along[rows, cols] + along_phase) / _STEP)
      edged = across[rows, cols] + across_phase + stair * _KICK
      mask = np.mod(edged, _PERIOD) < (_PERIOD * _DUTY)
      out = canvas[rows, cols]
      out[:] = magenta
      out[mask] = purple

  def _score_bar(self, unit):
    key = (self.home, self.away, self.score, self.clock, round(unit, 3))
    if self._score_sprite is not None and self._score_key == key:
      return self._score_sprite
    height = max(36, int(round(58 * unit)))
    team_font = _font('extra', 20 * unit)
    score_font = _font('extra', 32 * unit)
    clock_font = _font('bold', 18 * unit)
    home_w = _block_width(team_font, self.home, 18 * unit)
    away_w = _block_width(team_font, self.away, 18 * unit)
    score_text = '%d  –  %d' % (self.score[0], self.score[1])
    score_w = _block_width(score_font, score_text, 16 * unit)
    clock_text = '%02d:%02d' % (self.clock // 60, self.clock % 60)
    clock_w = _block_width(clock_font, clock_text, 14 * unit)
    cap = max(4, int(round(6 * unit)))
    total = cap + home_w + score_w + away_w + clock_w
    sprite = Image.new('RGB', (total, height), GREEN)
    draw = ImageDraw.Draw(sprite)
    x = 0
    draw.rectangle((x, 0, x + cap, height), fill=GREEN)
    x += cap
    _block(draw, x, 0, home_w, height, PURPLE, self.home, team_font, WHITE)
    x += home_w
    _block(draw, x, 0, score_w, height, GREEN, score_text, score_font, PURPLE)
    x += score_w
    _block(draw, x, 0, away_w, height, PURPLE, self.away, team_font, WHITE)
    x += away_w
    _block(draw, x, 0, clock_w, height, MAGENTA, clock_text, clock_font, WHITE)
    out = cv2.cvtColor(np.asarray(sprite), cv2.COLOR_RGB2BGR)
    self._score_sprite = out
    self._score_key = key
    return out

  def _lower_bar(self, unit, max_width):
    card = self.scorer
    key = (
        card['name'], card['shirt'], card['minute'], round(unit, 3), max_width,
        self.language)
    if self._lower_sprite is not None and self._lower_key == key:
      return self._lower_sprite
    height = max(52, int(round(86 * unit)))
    left_w = max(int(round(108 * unit)), int(round(height * 1.15)))
    shirt_font = _font('extra', 36 * unit)
    minute_font = _font('bold', 13 * unit)
    name = card['name']
    name_size = 30 * unit
    name_font = _font('extra', name_size)
    minute = languages.phrase(self.language, 'minute') % int(card['minute'])
    shirt = str(int(card['shirt']))
    pad = int(round(26 * unit))
    name_w, _, _, _ = _ink(name_font, name)
    while name_w + pad * 2 > max_width - left_w and name_size > 14 * unit:
      name_size -= 2
      name_font = _font('extra', name_size)
      name_w, _, _, _ = _ink(name_font, name)
    name_w = min(name_w + pad * 2, max(left_w, max_width - left_w))
    cap = max(4, int(round(6 * unit)))
    total = cap + left_w + int(name_w)
    sprite = Image.new('RGB', (total, height), GREEN)
    draw = ImageDraw.Draw(sprite)
    draw.rectangle((0, 0, cap, height), fill=MAGENTA)
    draw.rectangle((cap, 0, cap + left_w, height), fill=PURPLE)
    number_w, number_h, _, _ = _ink(shirt_font, shirt)
    _write(
        draw,
        cap + (left_w - number_w) // 2,
        int(height * 0.16),
        shirt,
        shirt_font,
        GREEN,
    )
    minute_w, _, _, _ = _ink(minute_font, minute)
    _write(
        draw,
        cap + (left_w - minute_w) // 2,
        int(height * 0.68),
        minute,
        minute_font,
        CYAN,
    )
    name_x = cap + left_w
    draw.rectangle((name_x, 0, total, height), fill=GREEN)
    drawn_w, drawn_h, _, _ = _ink(name_font, name)
    _write(
        draw,
        name_x + pad,
        (height - drawn_h) // 2,
        name,
        name_font,
        PURPLE,
    )
    out = cv2.cvtColor(np.asarray(sprite), cv2.COLOR_RGB2BGR)
    self._lower_sprite = out
    self._lower_key = key
    return out

  def _extend(self, canvas, sprite, x, y, progress, unit):
    if progress <= 0:
      return
    full = sprite.shape[1]
    show = full if progress >= 1 else max(6, int(round(full * progress)))
    show = min(show, full, canvas.shape[1] - x)
    row = min(sprite.shape[0], canvas.shape[0] - y)
    if show <= 0 or row <= 0 or x < 0 or y < 0:
      return
    canvas[y:y + row, x:x + show] = sprite[:row, :show]
    if progress < 1:
      lip = max(3, int(round(5 * unit)))
      lip_x = min(canvas.shape[1], x + show)
      lip_from = max(x, lip_x - lip)
      canvas[y:y + row, lip_from:lip_x] = _BGR[CYAN]


# How long the comparison holds the shared opening frame, and the last pair.
# 90 frames is a second and a half at 60fps, long enough to see they match.
COMPARE_HOLD = 90
COMPARE_TAIL = 48


class ComparePlate(object):
  """Side-by-side broadcast for one moment and the run that splits from it.

  The ground is green and purple, the other way around from the key-moment
  title. Both pictures use the same frame until the plays are allowed to move.
  """

  def __init__(self, home, away, minute, language='en'):
    self.home = side_label(home)
    self.away = side_label(away)
    self.language = languages.normalize(language)
    self.minute = None if minute is None else int(minute)
    self.clock = 0
    self.left_score = (0, 0)
    self.right_score = (0, 0)
    self._tick = 0
    self._open_i = 0
    self._close_i = None
    self._title_sprite = None
    self._title_key = None
    self._title_place = None
    self._card_buf = None
    self._canvas_buf = None
    self._text_cache = {}

  def set_state(self, clock, left_score, right_score):
    self.clock = max(0, int(clock))
    self.left_score = (int(left_score[0]), int(left_score[1]))
    self.right_score = (int(right_score[0]), int(right_score[1]))

  def begin_close(self):
    """The next stamps return to the title, then add the two results."""
    self._close_i = 0

  def stamp(self, left, right):
    self._tick += 1
    if self._close_i is not None:
      index = self._close_i
      self._close_i += 1
      return self._closing(left, right, index)
    if self._open_i < OPEN_FRAMES:
      index = self._open_i
      self._open_i += 1
      return self._opening(left, right, index)
    return self._split(left, right)

  def _opening(self, left, right, index):
    height, width = left.shape[:2]
    card = self._card(width, height)
    self._green_chevrons(card)
    held = index < OPEN_IN + OPEN_HOLD
    if held:
      fade = 1.0 if index >= OPEN_IN else _ease((index + 1) / float(OPEN_IN))
      self._paint_title(card, fade, False)
      return card
    gone = index - (OPEN_IN + OPEN_HOLD)
    progress = _ease((gone + 1) / float(OPEN_OUT))
    template = self._split(left, right)
    if progress >= 1.0:
      return template
    self._paint_title(card, max(0.0, 1.0 - progress * 1.6), False)
    x0 = int(round((1.0 - progress) * width * 0.5))
    y0 = int(round((1.0 - progress) * height * 0.5))
    x1 = width - x0
    y1 = height - y0
    if x1 > x0 and y1 > y0:
      card[y0:y1, x0:x1] = template[y0:y1, x0:x1]
    return card

  def _closing(self, left, right, index):
    height, width = left.shape[:2]
    card = self._card(width, height)
    self._green_chevrons(card)
    if index < CLOSE_IN:
      progress = _ease((index + 1) / float(CLOSE_IN))
      template = self._split(left, right)
      self._paint_title(card, min(1.0, progress * 1.6), True)
      remain = 1.0 - progress
      x0 = int(round((1.0 - remain) * width * 0.5))
      y0 = int(round((1.0 - remain) * height * 0.5))
      x1 = width - x0
      y1 = height - y0
      if x1 > x0 and y1 > y0:
        card[y0:y1, x0:x1] = template[y0:y1, x0:x1]
      return card
    if index < CLOSE_IN + CLOSE_HOLD:
      self._paint_title(card, 1.0, True)
      return card
    gone = index - (CLOSE_IN + CLOSE_HOLD)
    fade = 1.0 - _ease((gone + 1) / float(CLOSE_OUT))
    self._paint_title(card, fade, True)
    return card

  def _green_chevrons(self, canvas):
    """Green field, purple chevrons, traveling to the right."""
    height, width = canvas.shape[:2]
    along = _chevron_field(width, height)
    period = max(96.0, height * 0.30)
    phase = self._tick * 4.0
    purple = np.mod(along - phase, period) < period * 0.42
    canvas[:] = _BGR[GREEN]
    canvas[purple] = _BGR[PURPLE]

  def _split(self, left, right):
    """Two framed pictures on the chevron field, with one shared clock."""
    height, width = left.shape[:2]
    canvas = self._canvas(width, height)
    self._green_chevrons(canvas)
    margin = max(28, int(round(width * 0.045)))
    gap = max(22, int(round(width * 0.03)))
    card_w = (width - 2 * margin - gap) // 2
    card_w -= card_w % 2
    if card_w < 64:
      return canvas
    frame = max(8, int(round(height * 0.016)))
    label_h = max(28, int(round(height * 0.064)))
    score_h = max(26, int(round(height * 0.052)))
    inner_w = card_w - 2 * frame
    inner_h = max(36, int(round(inner_w * 9.0 / 16.0)))
    inner_h -= inner_h % 2
    # White margin above and below the score, so the green bar stays inside the card.
    card_h = label_h + inner_h + score_h + 2 * frame
    if card_h > height - 24:
      inner_h = max(36, height - 24 - label_h - score_h - 2 * frame)
      inner_h -= inner_h % 2
      card_h = label_h + inner_h + score_h + 2 * frame
    top = max(8, (height - card_h) // 2)
    left_x = margin
    right_x = width - margin - card_w
    white = _BGR[WHITE]
    canvas[top:top + card_h, left_x:left_x + card_w] = white
    canvas[top:top + card_h, right_x:right_x + card_w] = white
    picture_y = top + label_h
    self._place(canvas, left, left_x + frame, picture_y, inner_w, inner_h)
    self._place(canvas, right, right_x + frame, picture_y, inner_w, inner_h)
    self._caption(
        canvas, left_x, top, card_w, label_h,
        languages.phrase(self.language, 'reality'))
    self._caption(
        canvas, right_x, top, card_w, label_h,
        languages.phrase(self.language, 'alternate_outcome'))
    score_y = picture_y + inner_h + frame
    left_line = '%s  %d – %d  %s' % (
        self.home, self.left_score[0], self.left_score[1], self.away)
    right_line = '%s  %d – %d  %s' % (
        self.home, self.right_score[0], self.right_score[1], self.away)
    self._caption(
        canvas, left_x + frame, score_y, inner_w, score_h,
        left_line, fill=GREEN, ink=PURPLE)
    self._caption(
        canvas, right_x + frame, score_y, inner_w, score_h,
        right_line, fill=GREEN, ink=PURPLE)
    clock = '%02d:%02d' % (self.clock // 60, self.clock % 60)
    clock_h = max(22, int(round(height * 0.04)))
    clock_w = min(width // 5, max(90, int(round(width * 0.12))))
    self._caption(
        canvas, (width - clock_w) // 2, max(8, top - clock_h - 8),
        clock_w, clock_h, clock, fill=PURPLE, ink=WHITE)
    return canvas

  def _place(self, canvas, image, x, y, width, height):
    if image is None or width < 2 or height < 2:
      return
    picture = image
    if picture.shape[1] != width or picture.shape[0] != height:
      picture = cv2.resize(picture, (width, height), interpolation=cv2.INTER_AREA)
    row = min(height, canvas.shape[0] - y)
    col = min(width, canvas.shape[1] - x)
    if row <= 0 or col <= 0 or x < 0 or y < 0:
      return
    canvas[y:y + row, x:x + col] = picture[:row, :col]

  def _caption(self, canvas, x, y, width, height, text, fill=None, ink=PURPLE):
    if width < 8 or height < 8 or x < 0 or y < 0:
      return
    row = min(height, canvas.shape[0] - y)
    col = min(width, canvas.shape[1] - x)
    if row <= 0 or col <= 0:
      return
    key = (text, col, row, fill, ink)
    sprite = self._text_cache.get(key)
    if sprite is None:
      bg = WHITE if fill is None else fill
      image = Image.new('RGB', (col, row), bg)
      draw = ImageDraw.Draw(image)
      size = max(12, int(row * 0.52))
      font = _font('extra', size)
      text_w, _, _, _ = _ink(font, text)
      while text_w > col * 0.9 and size > 10:
        size -= 1
        font = _font('extra', size)
        text_w, _, _, _ = _ink(font, text)
      text_w, text_h, _, _ = _ink(font, text)
      _write(
          draw, (col - text_w) // 2, (row - text_h) // 2, text, font, ink)
      sprite = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
      if len(self._text_cache) > 24:
        self._text_cache.clear()
      self._text_cache[key] = sprite
    if fill is not None:
      canvas[y:y + row, x:x + col] = sprite
      return
    # A white card is already there. Paint only the glyphs.
    cover = np.any(sprite != _BGR[WHITE], axis=2)
    region = canvas[y:y + row, x:x + col]
    region[cover] = sprite[cover]

  def _title_block(self, width, height, with_result):
    key = (
        width, height, self.minute, with_result,
        self.left_score, self.right_score, self.language)
    if self._title_sprite is not None and self._title_key == key:
      return self._title_sprite, self._title_place
    word = languages.phrase(self.language, 'what_if')
    word_size = max(48, int(round(height * 0.13)))
    word_font = _font('extra', word_size)
    word_w, word_h, _, _ = _ink(word_font, word)
    while word_w > width * 0.86 and word_size > 36:
      word_size -= 4
      word_font = _font('extra', word_size)
      word_w, word_h, _, _ = _ink(word_font, word)
    minute_text = '' if self.minute is None else "%d'" % self.minute
    minute_font = _font('extra', max(22, int(round(height * 0.05))))
    minute_w, minute_h = (0, 0)
    if minute_text:
      minute_w, minute_h, _, _ = _ink(minute_font, minute_text)
    result_font = _font('extra', max(20, int(round(height * 0.042))))
    lines = []
    if with_result:
      lines = [
          '%s  %d – %d' % (
              (languages.phrase(self.language, 'reality_short'),) + self.left_score),
          '%s  %d – %d' % (
              (languages.phrase(self.language, 'alternate_short'),) + self.right_score),
      ]
    line_h = 0
    line_w = 0
    if lines:
      for line in lines:
        one_w, one_h, _, _ = _ink(result_font, line)
        line_w = max(line_w, one_w)
        line_h = max(line_h, one_h)
    bar_w = max(int(word_w * 0.28), 80)
    bar_h = max(6, int(round(height * 0.012)))
    gap = max(14, int(round(height * 0.026)))
    total_h = word_h + gap + bar_h
    if minute_text:
      total_h += gap + minute_h
    if lines:
      total_h += gap + len(lines) * line_h + (len(lines) - 1) * (gap // 2)
    total_w = max(word_w, bar_w, minute_w, line_w)
    sprite = Image.new('RGBA', (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sprite)
    _write(draw, (total_w - word_w) // 2, 0, word, word_font, WHITE)
    bar_y = word_h + gap
    bar_x = (total_w - bar_w) // 2
    draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), fill=PURPLE)
    cursor = bar_y + bar_h
    if minute_text:
      cursor += gap
      _write(
          draw, (total_w - minute_w) // 2, cursor, minute_text, minute_font, WHITE)
      cursor += minute_h
    if lines:
      cursor += gap
      for line in lines:
        one_w, one_h, _, _ = _ink(result_font, line)
        _write(
            draw, (total_w - one_w) // 2, cursor, line, result_font, WHITE)
        cursor += one_h + gap // 2
    raw = np.asarray(sprite)
    bgr = cv2.cvtColor(raw[:, :, :3], cv2.COLOR_RGB2BGR)
    alpha = raw[:, :, 3]
    place = ((width - total_w) // 2, (height - total_h) // 2)
    self._title_sprite = (bgr, alpha)
    self._title_key = key
    self._title_place = place
    return self._title_sprite, place

  def _paint_title(self, canvas, fade, with_result):
    if fade <= 0.0:
      return
    (bgr, alpha), (x, y) = self._title_block(
        canvas.shape[1], canvas.shape[0], with_result)
    x = int(x)
    y = int(y)
    row = min(bgr.shape[0], canvas.shape[0] - y)
    col = min(bgr.shape[1], canvas.shape[1] - x)
    if row <= 0 or col <= 0 or x < 0 or y < 0:
      return
    cover = alpha[:row, :col].astype(np.float32) * float(fade) / 255.0
    cover = cover[:, :, None]
    region = canvas[y:y + row, x:x + col]
    mixed = region.astype(np.float32) * (1.0 - cover) + bgr[:row, :col] * cover
    region[:] = mixed.astype(np.uint8)

  def _card(self, width, height):
    buf = self._card_buf
    if buf is None or buf.shape[0] != height or buf.shape[1] != width:
      buf = np.empty((height, width, 3), np.uint8)
      self._card_buf = buf
    return buf

  def _canvas(self, width, height):
    buf = self._canvas_buf
    if buf is None or buf.shape[0] != height or buf.shape[1] != width:
      buf = np.empty((height, width, 3), np.uint8)
      self._canvas_buf = buf
    return buf


def _block_width(font, text, pad):
  width, _, _, _ = _ink(font, text)
  return int(width + 2 * pad)


def _block(draw, x, y, width, height, fill, text, font, color):
  draw.rectangle((x, y, x + width, y + height), fill=fill)
  text_w, text_h, _, _ = _ink(font, text)
  _write(
      draw,
      x + (width - text_w) // 2,
      y + (height - text_h) // 2,
      text,
      font,
      color,
  )
