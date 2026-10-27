"""Run a live GRF match.

The engine plays every player. The OpenGL window is the picture. The view,
the lens, freeze, the touch feeds, and the match chat
are a transparent React panel on that same window. The panel gets state only. The picture is
not copied off the GPU. Set BRANCHPLAY_HIDE_WINDOW=1 to hide the window and
serve the pictures in the browser instead. SDL still has to be created on
the main thread, so the match loop runs there.

In the game window, drag looks around in Free, W A S D move, Q and E move
down and up, and Shift is faster. [ and ] change the view, L changes the
lens, and F freezes. The picture stays in the window.

One physics frame is 10ms, so a visible match is paced to 100 pictures
per second. Drawing faster than that would play the match fast.

Run from the repository root:

    DYLD_LIBRARY_PATH=.deps/prefix/lib GRF/.venv/bin/python viewer/watch.py
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import base64
import hashlib
import json
import math
import os
# Holding W A S D moves the camera. macOS otherwise opens the accent menu
# for a held letter. SDL reads this before it creates the window.
os.environ['SDL_MAC_PRESS_AND_HOLD'] = '0'
# The match is a Python process. After a crash, macOS offers to restore
# that process's windows, and the offer itself can abort the next launch.
os.environ['ApplePersistenceIgnoreState'] = 'YES'
import pickle
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time

import broadcast
import formations
import languages
import match_chat
import moment_page
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

import cv2
import numpy as np

import saves
from gfootball.env import config as football_config
from gfootball.env import football_env_core


HOST = '127.0.0.1'
PORT = 8000
PHYSICS_FRAME_SECONDS = 0.01
# The 11v11 scenario lasts 3000 steps of 10 physics frames. This page steps
# one physics frame at a time, so the same match is 30000 frames.
FULL_MATCH_FRAMES = 30000

WS_GUID = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

PAGE = """<!DOCTYPE html>
<meta charset="utf-8">
<title>BranchPlay</title>
<style>
  html, body { margin: 0; height: 100%; background: #000; color: #fff;
    font: 14px sans-serif; }
  canvas { display: block; width: 100%; height: calc(100% - 36px); }
  #note { display: none; margin: 0; padding: 8px 12px; }
  body.window-controls { height: auto; }
  body.window-controls canvas { display: none; }
  body.window-controls #note { display: block; }
  body.window-controls #bar { height: auto; min-height: 36px;
    flex-wrap: wrap; padding: 8px 12px; }
  #bar { display: flex; align-items: center; gap: 16px; height: 36px;
    padding: 0 12px; background: #111; }
  #bar span { white-space: nowrap; overflow: hidden; }
  select, label, button { font: inherit; }
  select, button { color: #000; background: #fff; }
  button { border: 0; padding: 2px 8px; }
  button[aria-pressed="true"] { outline: 2px solid #fff; }
</style>
<p id="note"></p>
<canvas id="pitch"></canvas>
<div id="bar">
  <label>View
    <select id="view">
      <option value="-1">Broadcast</option>
      <option value="-2">Action</option>
      <option value="-3">Free</option>
    </select>
  </label>
  <label>Lens
    <select id="lens">
      <option value="0">Eyes</option>
      <option value="1">Long</option>
    </select>
  </label>
  <button type="button" id="freeze">Freeze</button>
  <span id="fly"></span>
</div>
<script>
const pictureInWindow = false;
const canvas = document.getElementById('pitch');
const ctx = canvas.getContext('2d');
let socket = null;
let pending = null;
let drawing = false;

function fit(bitmap) {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.round(canvas.clientWidth * ratio);
  const height = Math.round(canvas.clientHeight * ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const scale = Math.min(width / bitmap.width, height / bitmap.height);
  const dw = bitmap.width * scale;
  const dh = bitmap.height * scale;
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(bitmap, (width - dw) / 2, (height - dh) / 2, dw, dh);
}

async function paint(buffer) {
  pending = buffer;
  if (drawing) return;
  drawing = true;
  while (pending) {
    const latest = pending;
    pending = null;
    try {
      const bitmap = await createImageBitmap(
          new Blob([latest], {type: 'image/jpeg'}));
      fit(bitmap);
      bitmap.close();
    } catch (err) {}
  }
  drawing = false;
}

const freeCam = {x: 0, y: -32, z: 14, yaw: Math.PI / 2, pitch: -0.35};
const held = {};
let dragX = 0;
let dragY = 0;

function syncLens() {
  const value = document.getElementById('view').value;
  const free = value === '-3';
  document.getElementById('lens').disabled =
      value === '-1' || value === '-2' || free;
  document.getElementById('fly').textContent = free
      ? (pictureInWindow
          ? 'In the game window: drag to look. W A S D move. Q down, E up. Shift is faster.'
          : 'Drag to look. W A S D move. Q down, E up. Shift is faster.')
      : '';
  canvas.style.cursor = free ? 'grab' : '';
}

function cameraChoice() {
  const value = document.getElementById('view').value;
  const lens = Number(document.getElementById('lens').value);
  if (value === '-1') return {team: -1, player: 0, lens: 0};
  if (value === '-2') return {team: -1, player: 0, lens: 2};
  if (value === '-3') {
    const choice = {team: -1, player: 0, lens: 3};
    // The game window owns the pose. Sending the page's copy would pull
    // the camera back to where the page last left it.
    if (!pictureInWindow) {
      choice.x = freeCam.x;
      choice.y = freeCam.y;
      choice.z = freeCam.z;
      choice.yaw = freeCam.yaw;
      choice.pitch = freeCam.pitch;
    }
    return choice;
  }
  const parts = value.split(':');
  return {team: Number(parts[0]), player: Number(parts[1]), lens: lens};
}

function moveFree(dt) {
  if (pictureInWindow) return false;
  if (document.getElementById('view').value !== '-3') return false;
  let moved = false;
  if (dragX || dragY) {
    freeCam.yaw -= dragX * 0.005;
    freeCam.pitch = Math.max(-1.15, Math.min(1.15,
        freeCam.pitch - dragY * 0.005));
    dragX = 0;
    dragY = 0;
    moved = true;
  }
  const speed = (held.shift ? 40 : 18) * dt;
  const going = held.w || held.a || held.s || held.d || held.q || held.e;
  if (going && speed > 0) {
    const c = Math.cos(freeCam.yaw);
    const s = Math.sin(freeCam.yaw);
    if (held.w) { freeCam.x += c * speed; freeCam.y += s * speed; }
    if (held.s) { freeCam.x -= c * speed; freeCam.y -= s * speed; }
    if (held.d) { freeCam.x += s * speed; freeCam.y -= c * speed; }
    if (held.a) { freeCam.x -= s * speed; freeCam.y += c * speed; }
    if (held.e) freeCam.z += speed;
    if (held.q) freeCam.z -= speed;
    freeCam.x = Math.max(-100, Math.min(100, freeCam.x));
    freeCam.y = Math.max(-80, Math.min(80, freeCam.y));
    freeCam.z = Math.max(0.4, Math.min(60, freeCam.z));
    moved = true;
  }
  return moved;
}

let freezeKnown = false;
let localUntil = 0;

function markLocal() {
  localUntil = Date.now() + 600;
}

function viewValue(status) {
  if (!status.view) return null;
  if (status.view.lens === 3) return '-3';
  if (status.view.lens === 2 && status.view.team < 0) return '-2';
  if (status.view.team === 0 || status.view.team === 1) {
    return status.view.team + ':' + status.view.player;
  }
  return '-1';
}

function hasOption(select, value) {
  for (let i = 0; i < select.options.length; i++) {
    if (select.options[i].value === value) return true;
  }
  return false;
}

function applyStatus(status) {
  const view = document.getElementById('view');
  const value = viewValue(status);
  if (value && hasOption(view, value) && view.value !== value &&
      document.activeElement !== view) {
    view.value = value;
    syncLens();
  }
  const lens = document.getElementById('lens');
  if (status.view && (status.view.lens === 0 || status.view.lens === 1) &&
      document.activeElement !== lens &&
      lens.value !== String(status.view.lens)) {
    lens.value = String(status.view.lens);
  }
  if (freezeKnown) {
    const paused = !!status.frozen;
    const shown = document.getElementById('freeze')
        .getAttribute('aria-pressed') === 'true';
    if (paused !== shown) applyFreeze(paused);
  }
}

function applyFreeze(paused) {
  const button = document.getElementById('freeze');
  button.setAttribute('aria-pressed', paused ? 'true' : 'false');
  button.textContent = paused ? 'Resume' : 'Freeze';
}

function sendCamera() {
  if (!socket || socket.readyState !== 1) return;
  const message = {camera: cameraChoice()};
  // A fresh page must not resume a frozen match before it has read the state.
  // After that, every message repeats the button, so a reconnect keeps it.
  if (freezeKnown) {
    message.frozen = document.getElementById('freeze')
        .getAttribute('aria-pressed') === 'true';
  }
  socket.send(JSON.stringify(message));
}

function fillView(players) {
  const view = document.getElementById('view');
  const current = view.value;
  while (view.options.length > 3) view.remove(3);
  players.forEach(function (player) {
    const option = document.createElement('option');
    option.value = player.team + ':' + player.player;
    option.textContent = player.name;
    view.appendChild(option);
  });
  if (current) view.value = current;
  syncLens();
}

function loadRoster() {
  fetch('/state').then(function (response) { return response.json(); })
      .then(function (status) {
        if (!status.players || !status.players.length) {
          setTimeout(loadRoster, 300);
          return;
        }
        fillView(status.players);
        if (pictureInWindow) applyStatus(status);
        if (!freezeKnown) {
          applyFreeze(!!status.frozen);
          freezeKnown = true;
          sendCamera();
        }
      }).catch(function () { setTimeout(loadRoster, 300); });
}

document.getElementById('view').addEventListener('change', function () {
  markLocal();
  syncLens();
  sendCamera();
});
document.getElementById('lens').addEventListener('change', function () {
  markLocal();
  sendCamera();
});
document.getElementById('freeze').addEventListener('click', function () {
  const button = document.getElementById('freeze');
  markLocal();
  freezeKnown = true;
  applyFreeze(button.getAttribute('aria-pressed') !== 'true');
  sendCamera();
});
syncLens();
loadRoster();

window.addEventListener('keydown', function (event) {
  if (event.target && event.target.tagName === 'SELECT') return;
  const key = event.key.toLowerCase();
  if (pictureInWindow && key === 'f') {
    const button = document.getElementById('freeze');
    markLocal();
    freezeKnown = true;
    applyFreeze(button.getAttribute('aria-pressed') !== 'true');
    sendCamera();
    event.preventDefault();
    return;
  }
  if (document.getElementById('view').value !== '-3') return;
  if (key === 'shift') held.shift = true;
  else held[key] = true;
  if ('wasdqe'.indexOf(key) !== -1) event.preventDefault();
});
window.addEventListener('keyup', function (event) {
  const key = event.key.toLowerCase();
  if (key === 'shift') held.shift = false;
  else held[key] = false;
});
window.addEventListener('blur', function () {
  Object.keys(held).forEach(function (key) { held[key] = false; });
});
canvas.addEventListener('pointerdown', function (event) {
  if (document.getElementById('view').value !== '-3') return;
  if (event.button !== 0) return;
  canvas.setPointerCapture(event.pointerId);
  canvas.style.cursor = 'grabbing';
});
canvas.addEventListener('pointermove', function (event) {
  if (document.getElementById('view').value !== '-3') return;
  if (!canvas.hasPointerCapture(event.pointerId)) return;
  dragX += event.movementX;
  dragY += event.movementY;
});
canvas.addEventListener('pointerup', function () {
  canvas.style.cursor =
      document.getElementById('view').value === '-3' ? 'grab' : '';
});
let lastFly = 0;
function fly(now) {
  const dt = Math.min(0.05, lastFly ? (now - lastFly) / 1000 : 0.016);
  lastFly = now;
  if (moveFree(dt)) sendCamera();
  requestAnimationFrame(fly);
}
requestAnimationFrame(fly);

function connect() {
  const protocol = location.protocol === 'https:' ? 'wss://' : 'ws://';
  const next = new WebSocket(protocol + location.host + '/session');
  next.binaryType = 'arraybuffer';
  socket = next;
  next.onopen = function () {
    if (pictureInWindow && !freezeKnown) return;
    sendCamera();
  };
  next.onmessage = function (event) {
    if (typeof event.data !== 'string') paint(event.data);
  };
  next.onclose = function () {
    if (socket === next) setTimeout(connect, 400);
  };
}
let statusTicket = 0;

function watchStatus() {
  if (Date.now() < localUntil) {
    setTimeout(watchStatus, 300);
    return;
  }
  const ticket = ++statusTicket;
  fetch('/state').then(function (response) { return response.json(); })
      .then(function (status) {
        if (ticket !== statusTicket || Date.now() < localUntil) return;
        applyStatus(status);
      }).catch(function () {});
  setTimeout(watchStatus, 300);
}

if (pictureInWindow) {
  document.body.classList.add('window-controls');
  document.getElementById('note').textContent =
      'The match is in the game window. [ and ] change the view. L changes the lens. F freezes.';
  watchStatus();
}
connect();
</script>
"""


class LiveMatch(object):
  """The one running match, and the browser currently controlling it."""

  def __init__(self):
    self._lock = threading.Lock()
    self._send_lock = threading.Lock()
    self._connection = None
    self._writer = None
    self._generation = 0
    self._keys = set()
    self._camera_team = -1
    self._camera_player = 0
    self._camera_lens = 0
    self._free = (0.0, -32.0, 14.0, 1.5707963, -0.35)
    self._frozen = False
    self._camera_generation = 0
    self._camera_applied = 0
    self._frozen_generation = 0
    self._frozen_applied = 0
    self._fullscreen = False
    self._fullscreen_generation = 0
    self._fullscreen_applied = 0
    self._band = 0
    self._band_generation = 0
    self._band_applied = 0
    self._restart_generation = 0
    self._home_generation = 0
    self._home_applied = 0
    self._restart_applied = 0
    self._quit = False
    self._callouts = True
    self._callouts_generation = 0
    self._callouts_applied = 0
    self._menu = True
    self._menu_generation = 0
    self._menu_applied = 0
    self._simulate_generation = 0
    self._simulate_applied = 0
    self._simulate_deterministic = False
    self._branch_generation = 0
    self._branch_applied = 0
    self._branch_count = 2
    self._branch_minutes = None
    self._branch_clock = None
    self._branch_seconds = None
    self._formation_generation = 0
    self._formation_applied = 0
    self._formation_sides = {}
    self._edit_generation = 0
    self._edit_applied = 0
    self._edit_action = ''
    self._edit_team = None
    self._edit_phase = ''
    self._edit_origin = None
    self._edit_view = None
    self._base_formation = None
    self._clear_generation = 0
    self._clear_applied = 0
    self._moment_generation = 0
    self._moment_applied = 0
    self._moment_start = 0
    self._moment_end = 0
    self._moment_id = None
    self._moment_stop = False
    self._clip_language = 'en'
    self._clip_path = None
    self._clip_done = False
    self._compare = False
    self._brief_generation = 0
    self._brief_applied = 0
    self._brief_start = 0
    self._brief_end = 0
    self._brief_stop = False
    self._brief = None
    self._preview_path = None
    self._moments = {}
    self._line_generation = 0
    self._line_applied = 0
    self._line_request = ''
    self._open_generation = 0
    self._open_applied = 0
    self._open_id = ''
    self._remove_sim_generation = 0
    self._remove_sim_applied = 0
    self._remove_sim_id = ''
    self._viewing = False
    self._log = []
    self._log_seen = set()
    self._future = None
    self._roster = []
    self._ball = None
    self._chat_view = {}
    self._chat_history = []
    self._chat_busy = False
    self._boxes = None
    self._boxes_generation = 0
    self._boxes_applied = 0
    self._hidden_players = []
    self._hidden_ball = False
    self._hidden_generation = 0
    self._hidden_applied = 0
    self._lines = []
    self._lines_generation = 0
    self._lines_applied = 0
    self._timeline = []
    self._span = 0
    self._scrub_to = 0
    self._scrub_generation = 0
    self._scrub_applied = 0
    self._played_until = None
    self._branches = []
    self._line_id = None
    self._sim_id = ''
    self._saved = None
    self._frame = threading.Condition()
    self._jpeg = None
    self._sequence = 0
    self._status = {}

  def attach(self, connection, writer):
    with self._lock:
      previous = self._connection
      self._connection = connection
      self._writer = writer
      self._keys = set()
      self._generation += 1
      generation = self._generation
    if previous is not None and previous is not connection:
      try:
        previous.shutdown(socket.SHUT_RDWR)
      except OSError:
        pass
    return generation

  def detach(self, generation):
    with self._lock:
      if self._generation == generation:
        self._connection = None
        self._writer = None
        self._keys = set()

  def set_keys(self, names):
    with self._lock:
      self._keys = set(names)

  def keys(self):
    with self._lock:
      return set(self._keys)

  def set_camera(self, choice):
    try:
      team = int(choice.get('team', -1))
      player = int(choice.get('player', 0))
      lens = int(choice.get('lens', 0))
    except (TypeError, ValueError, AttributeError):
      return
    if team not in (-1, 0, 1) or player < 0 or player > 10:
      return
    if team == -1:
      if lens not in (2, 3):
        lens = 0
    elif lens not in (0, 1):
      lens = 0
    free = None
    if lens == 3 and 'x' in choice:
      free = (
          _bounded(choice.get('x'), -100.0, 100.0, 0.0),
          _bounded(choice.get('y'), -80.0, 80.0, -32.0),
          _bounded(choice.get('z'), 0.4, 60.0, 14.0),
          _bounded(choice.get('yaw'), -1.0e6, 1.0e6, 1.5707963),
          _bounded(choice.get('pitch'), -1.15, 1.15, -0.35),
      )
    with self._lock:
      self._camera_team = team
      self._camera_player = player
      self._camera_lens = lens
      self._camera_generation += 1
      if free is not None:
        self._free = free

  def camera(self):
    with self._lock:
      return (self._camera_team, self._camera_player, self._camera_lens,
              self._free[0], self._free[1], self._free[2],
              self._free[3], self._free[4])

  def set_free(self, x, y, z, yaw, pitch):
    pose = (
        _bounded(x, -100.0, 100.0, 0.0),
        _bounded(y, -80.0, 80.0, -32.0),
        _bounded(z, 0.4, 60.0, 14.0),
        _bounded(yaw, -1.0e6, 1.0e6, 1.5707963),
        _bounded(pitch, -1.15, 1.15, -0.35),
    )
    with self._lock:
      self._free = pose

  def set_frozen(self, frozen):
    with self._lock:
      self._frozen = bool(frozen)
      self._frozen_generation += 1

  def frozen(self):
    with self._lock:
      return self._frozen

  def take_camera_command(self):
    """The next view the overlay asked for. None if it has not changed."""
    with self._lock:
      if self._camera_generation == self._camera_applied:
        return None
      self._camera_applied = self._camera_generation
      return (self._camera_team, self._camera_player, self._camera_lens)

  def take_frozen_command(self):
    """The next freeze the overlay asked for. None if it has not changed."""
    with self._lock:
      if self._frozen_generation == self._frozen_applied:
        return None
      self._frozen_applied = self._frozen_generation
      return self._frozen

  def set_fullscreen(self, fullscreen):
    with self._lock:
      self._fullscreen = bool(fullscreen)
      self._fullscreen_generation += 1

  def take_fullscreen_command(self):
    """The next fullscreen choice. None if the overlay has not asked again."""
    with self._lock:
      if self._fullscreen_generation == self._fullscreen_applied:
        return None
      self._fullscreen_applied = self._fullscreen_generation
      return self._fullscreen

  def set_bottom_band(self, points):
    """How tall the timeline band is, in window points."""
    try:
      points = int(points)
    except (TypeError, ValueError):
      return
    points = max(0, min(420, points))
    with self._lock:
      if points == self._band:
        return
      self._band = points
      self._band_generation += 1

  def take_bottom_band(self):
    """The next timeline height. None if the page has not asked again."""
    with self._lock:
      if self._band_generation == self._band_applied:
        return None
      self._band_applied = self._band_generation
      return self._band

  def request_restart(self):
    """Ask the match loop to start again from the kickoff."""
    with self._lock:
      self._restart_generation += 1

  def request_home(self):
    """Ask the match loop to leave the simulation and show the menu."""
    with self._lock:
      self._home_generation += 1
    self.request_brief_stop()

  def home_pending(self):
    with self._lock:
      return self._home_generation != self._home_applied

  def take_home(self):
    """True once for each request to return to the menu."""
    with self._lock:
      if self._home_generation == self._home_applied:
        return False
      self._home_applied = self._home_generation
      return True

  def request_simulate(self, deterministic=False):
    """Play a new match without drawing it, then save that match."""
    with self._lock:
      self._simulate_deterministic = bool(deterministic)
      self._simulate_generation += 1

  def take_simulate(self):
    """The next save the overlay asked for. None if it has not asked.

    True asks for a fixed seed. False asks for a new random seed.
    """
    with self._lock:
      if self._simulate_generation == self._simulate_applied:
        return None
      self._simulate_applied = self._simulate_generation
      return bool(self._simulate_deterministic)

  def request_open(self, sim_id):
    """Ask the match loop to play a saved match from its kickoff."""
    with self._lock:
      self._open_id = str(sim_id or '')
      self._open_generation += 1

  def take_open(self):
    """The next saved match to open. None if the overlay has not asked."""
    with self._lock:
      if self._open_generation == self._open_applied:
        return None
      self._open_applied = self._open_generation
      return self._open_id

  def request_remove_simulation(self, sim_id):
    """Ask the match loop to delete one saved match."""
    with self._lock:
      self._remove_sim_id = str(sim_id or '')
      self._remove_sim_generation += 1

  def take_remove_simulation(self):
    """The next saved match to delete. None if the overlay has not asked."""
    with self._lock:
      if self._remove_sim_generation == self._remove_sim_applied:
        return None
      self._remove_sim_applied = self._remove_sim_generation
      return self._remove_sim_id

  def set_future(self, rows):
    """The saved touch list for this kickoff. None when this match has none."""
    with self._lock:
      copied = None if rows is None else [dict(row) for row in rows]
      self._future = copied
      self._saved = None if copied is None else [dict(row) for row in copied]

  def set_timeline(self, marks, end_clock):
    """Minute snapshots for the save now on screen. Empty hides the scrubber."""
    with self._lock:
      self._timeline = list(marks or [])
      self._span = int(end_clock or 0)
      self._played_until = None

  def span(self):
    with self._lock:
      node = self._node(self._line_id)
      if node is not None:
        return int(node['end_clock'])
      return int(self._span)

  def base_span(self):
    """The original match length. A short branch does not shorten this."""
    with self._lock:
      return int(self._span)

  def timeline(self):
    with self._lock:
      return self._timeline, int(self._span)

  def set_sim(self, sim_id):
    with self._lock:
      self._sim_id = str(sim_id or '')

  def sim_id(self):
    with self._lock:
      return self._sim_id

  def can_branch(self):
    with self._lock:
      return bool(self._viewing and self._sim_id and self._span > 0)

  def set_branches(self, rows):
    with self._lock:
      self._branches = [dict(row) for row in rows or []]
      self._line_id = None

  def drop_branches(self):
    """Forget every branch and return to the base match. '' when there is no save."""
    with self._lock:
      sim = self._sim_id
      if not self._viewing or not sim:
        return ''
      on_branch = bool(self._line_id)
      self._branches = []
      if on_branch:
        self._line_id = None
        self._played_until = None
        if self._saved is None:
          self._future = None
        else:
          self._future = [dict(row) for row in self._saved]
      return sim

  def request_clear_branches(self):
    with self._lock:
      self._clear_generation += 1

  def take_clear_branches(self):
    with self._lock:
      if self._clear_generation == self._clear_applied:
        return False
      self._clear_applied = self._clear_generation
      return True

  def add_branch(self, row):
    with self._lock:
      self._branches = [
          item for item in self._branches if item.get('id') != row.get('id')]
      self._branches.append(dict(row))

  def next_branch_id(self):
    with self._lock:
      used = []
      for row in self._branches:
        try:
          used.append(int(row.get('id')))
        except (TypeError, ValueError):
          continue
      return str((max(used) if used else 0) + 1)

  def line_id(self):
    with self._lock:
      return self._line_id or ''

  def branch_clock(self, line_id):
    with self._lock:
      node = self._node(line_id)
      if node is None:
        return 0
      return int(node['clock'])

  def branch_menu(self):
    with self._lock:
      menu = []
      for row in self._branches:
        if not saves.shows_on_timeline(row):
          continue
        menu.append({
            'id': row.get('id'),
            'parent': row.get('parent') or '',
            'clock': int(row.get('clock') or 0),
            'end_clock': int(row.get('end_clock') or 0),
            'score': list(row.get('score') or [0, 0]),
            'minutes': row.get('minutes'),
        })
      return menu

  def marks_for(self, seconds):
    """Snapshots that cover this clock on the line now on screen."""
    with self._lock:
      node = self._node(self._line_id)
      while node is not None and int(node.get('clock') or 0) > int(seconds):
        node = self._node(node.get('parent'))
      if node is None:
        return self._timeline
      return node.get('marks') or self._timeline

  def set_line(self, line_id):
    """Show the base match, or one saved branch. False if that branch is gone."""
    with self._lock:
      wanted = str(line_id or '')
      if wanted and self._node(wanted) is None:
        return False
      self._line_id = wanted or None
      self._played_until = None
      self._future = self._merged(self._node(self._line_id))
      return True

  def request_branch(self, count, minutes, clock=None, seconds=None):
    count, minutes = _branch_bounds(count, minutes)
    target = None
    if clock not in (None, ''):
      try:
        target = int(clock)
      except (TypeError, ValueError):
        target = None
      if target is not None and (target < 0 or target > 200 * 60):
        target = None
    span = None
    if seconds not in (None, ''):
      try:
        span = int(seconds)
      except (TypeError, ValueError):
        span = None
      if span is not None:
        span = max(1, min(90 * 60, span))
    with self._lock:
      self._branch_count = count
      self._branch_minutes = minutes
      self._branch_clock = target
      self._branch_seconds = span
      self._branch_generation += 1

  def clip_language(self):
    """The language chosen for the article, the video, and the counterfactual."""
    with self._lock:
      return self._clip_language or 'en'

  def request_moment(self, start, end, clip_id=None, language=None):
    """Play one saved stretch in the panel. This does not branch."""
    try:
      start = int(start)
      end = int(end)
    except (TypeError, ValueError):
      return
    if start < 0 or end < start or end > 200 * 60:
      return
    try:
      clip_id = int(clip_id)
    except (TypeError, ValueError):
      clip_id = None
    with self._lock:
      self._moment_start = start
      self._moment_end = end
      self._moment_id = clip_id
      self._moment_stop = False
      self._clip_done = False
      self._compare = False
      self._clip_language = languages.normalize(language)
      self._moment_generation += 1
      self._brief_stop = True
      self._brief = None
      preview = self._preview_path
      self._preview_path = None
    _delete_clip(preview)

  def moment_id(self):
    with self._lock:
      return self._moment_id

  def finish_clip(self):
    """The panel has finished the video, or the user closed it."""
    with self._lock:
      self._clip_done = True

  def request_compare(self):
    """The panel asked for a counterfactual of the clip now on screen."""
    with self._lock:
      self._compare = True

  def take_compare(self):
    with self._lock:
      wanted = self._compare
      self._compare = False
      return wanted

  def clip_finished(self):
    with self._lock:
      return self._clip_done

  def remember_clip(self, path):
    with self._lock:
      previous = self._clip_path
      self._clip_path = path
    if previous and previous != path:
      _delete_clip(previous)

  def clear_clip(self, path):
    with self._lock:
      if self._clip_path == path:
        self._clip_path = None

  def clip_file(self, name):
    """The mp4 currently being played, or None."""
    if not isinstance(name, str) or not name or name != os.path.basename(name):
      return None
    with self._lock:
      candidates = (self._clip_path, self._preview_path)
    for path in candidates:
      if path and os.path.basename(path) == name and os.path.isfile(path):
        return path
    return None

  def take_moment(self):
    """The next key-moment playback. None if the overlay has not asked."""
    with self._lock:
      if self._moment_generation == self._moment_applied:
        return None
      self._moment_applied = self._moment_generation
      return (self._moment_start, self._moment_end, self._moment_generation)

  def request_brief(self, start, end, brief_id=None, language=None):
    """Open the article for one stretch. This does not record the clip."""
    try:
      start = int(start)
      end = int(end)
    except (TypeError, ValueError):
      return
    if start < 0 or end < start or end > 200 * 60:
      return
    try:
      brief_id = int(brief_id)
    except (TypeError, ValueError):
      brief_id = None
    with self._lock:
      self._brief_start = start
      self._brief_end = end
      self._brief_stop = False
      self._clip_language = languages.normalize(language)
      self._brief = {
          'id': brief_id,
          'language': self._clip_language,
          'title': languages.phrase(self._clip_language, 'key_moment'),
          'span': moment_page.span_label(start, end),
          'lead': '',
          'preview': '',
          'phase': 'writing',
          'progress': 0,
      }
      self._brief_generation += 1

  def take_brief(self):
    """The next article. None if the page has not asked, or it was closed."""
    with self._lock:
      if self._brief_generation == self._brief_applied:
        return None
      self._brief_applied = self._brief_generation
      if self._brief_stop or not self._brief:
        return None
      return (self._brief_start, self._brief_end, self._brief_generation)

  def request_brief_stop(self):
    with self._lock:
      self._brief_stop = True
      self._brief = None
      path = self._preview_path
      self._preview_path = None
    _delete_clip(path)

  def brief_active(self, token):
    with self._lock:
      return self._brief_generation == token and not self._brief_stop

  def brief_view(self):
    with self._lock:
      if not self._brief:
        return None
      return dict(self._brief)

  def set_brief(self, **fields):
    with self._lock:
      if self._brief_stop or not self._brief:
        return
      for key in ('title', 'span', 'lead', 'preview', 'phase'):
        if key in fields and fields[key] is not None:
          self._brief[key] = fields[key]
      if 'progress' in fields:
        try:
          progress = float(fields['progress'])
        except (TypeError, ValueError):
          progress = None
        if progress is not None:
          self._brief['progress'] = round(max(0.0, min(1.0, progress)), 4)

  def remember_preview(self, path):
    with self._lock:
      previous = self._preview_path
      self._preview_path = path
    if previous and previous != path:
      _delete_clip(previous)

  def drop_preview(self):
    with self._lock:
      path = self._preview_path
      self._preview_path = None
    _delete_clip(path)

  def request_moment_stop(self):
    with self._lock:
      self._moment_stop = True

  def moment_active(self, token):
    with self._lock:
      return self._moment_generation == token and not self._moment_stop

  def moment_replaced(self, token):
    """True when a newer playback was asked for while this one was running."""
    with self._lock:
      return self._moment_generation != token

  def touch_list(self):
    """A copy of the touches for the line on screen."""
    with self._lock:
      rows = self._future if self._future is not None else self._saved
      if not rows:
        return []
      return [dict(row) for row in rows]

  def possession(self, clock):
    """Each team's share of the ball for the line on screen, up to this clock."""
    with self._lock:
      rows = self._future if self._future is not None else self._saved
      return _possession_share(rows, clock)

  def take_branch(self):
    """The next branch request. None if the overlay has not asked.

    The third value is a match clock to restore before the branch, or None
    to start from the moment already on screen.
    """
    with self._lock:
      if self._branch_generation == self._branch_applied:
        return None
      self._branch_applied = self._branch_generation
      return (self._branch_count, self._branch_minutes,
              self._branch_clock, self._branch_seconds)

  def request_formation(self, sides):
    """Ask the match loop to stand these shapes and hold the picture."""
    cleaned = {}
    for key, name in (sides or {}).items():
      try:
        team = int(key)
      except (TypeError, ValueError):
        continue
      if team not in (0, 1) or name not in formations.FORMATIONS:
        continue
      cleaned[team] = name
    if not cleaned:
      return
    with self._lock:
      self._formation_sides = cleaned
      self._formation_generation += 1

  def take_formation(self):
    """The next formation request. None if the chat has not asked."""
    with self._lock:
      if self._formation_generation == self._formation_applied:
        return None
      self._formation_applied = self._formation_generation
      return dict(self._formation_sides)

  def request_edit(self, action, team=None):
    """Ask the match loop to start, drop, commit, play, add, or remove."""
    if action not in ('on', 'off', 'commit', 'play', 'add', 'remove', 'dismiss'):
      return
    with self._lock:
      self._edit_action = action
      self._edit_team = None if team is None else int(team)
      self._edit_generation += 1

  def take_edit(self):
    """The next edit request. None if the overlay has not asked."""
    with self._lock:
      if self._edit_generation == self._edit_applied:
        return None
      self._edit_applied = self._edit_generation
      return (self._edit_action, self._edit_team)

  def line_exists(self, line_id):
    """True for the base match, or a branch that is still saved."""
    with self._lock:
      wanted = str(line_id or '')
      if not wanted:
        return True
      return self._node(wanted) is not None

  def line_added(self):
    """Extra players recorded on the line now on screen."""
    with self._lock:
      node = self._node(self._line_id)
      if node is None:
        return []
      rows = node.get('added') or []
      return [dict(row) for row in rows if isinstance(row, dict)]

  def set_edit_phase(self, phase):
    with self._lock:
      self._edit_phase = phase or ''

  def edit_phase(self):
    with self._lock:
      return self._edit_phase

  def set_edit_origin(self, blob):
    """The snapshot from before this edit. The match loop is the only writer."""
    with self._lock:
      self._edit_origin = blob

  def edit_origin(self):
    with self._lock:
      return self._edit_origin

  def set_edit_view(self, view):
    """The camera to put back when an edit is dropped."""
    with self._lock:
      self._edit_view = view

  def edit_view(self):
    with self._lock:
      return self._edit_view

  def set_base_formation(self, shape):
    """The shape loaded with the match, before any formation branch."""
    with self._lock:
      self._base_formation = shape or None

  def base_formation(self):
    with self._lock:
      if not self._base_formation:
        return None
      return {
          team: [dict(row) for row in rows]
          for team, rows in self._base_formation.items()
      }

  def line_formation(self):
    """The shape stored on the branch on screen. None on the base match."""
    with self._lock:
      node = self._node(self._line_id)
      if node is None:
        return None
      shape = node.get('formation')
      if not shape:
        return None
      return {
          team: [dict(row) for row in rows]
          for team, rows in shape.items()
      }

  def moments(self):
    """Key moments for the timeline on screen."""
    with self._lock:
      key = self._line_id or ''
      return [dict(row) for row in self._moments.get(key, [])]

  def moment_map(self):
    """Key moments for every timeline. '' is the base match."""
    with self._lock:
      return {
          key: [dict(row) for row in rows]
          for key, rows in self._moments.items()
      }

  def set_moments(self, rows):
    """Key moments for the save now on screen. A list belongs to the base match."""
    with self._lock:
      self._moments = saves._moment_map(rows)

  def request_line(self, line_id):
    with self._lock:
      self._line_request = '' if line_id is None else str(line_id)
      self._line_generation += 1

  def take_line(self):
    """The next branch to show. '' is the base match. None if unchanged."""
    with self._lock:
      if self._line_generation == self._line_applied:
        return None
      self._line_applied = self._line_generation
      return self._line_request

  def _node(self, line_id):
    if not line_id:
      return None
    for row in self._branches:
      if str(row.get('id')) == str(line_id):
        return row
    return None

  def _merged(self, node):
    """Base touches up to a fork, then that branch's own touches."""
    if self._saved is None:
      return None
    if node is None:
      return [dict(row) for row in self._saved]
    chain = []
    seen = set()
    cursor = node
    while cursor is not None and cursor.get('id') not in seen:
      seen.add(cursor.get('id'))
      chain.append(cursor)
      cursor = self._node(cursor.get('parent'))
    chain.reverse()
    rows = []
    source = self._saved
    for item in chain:
      cut = int(item.get('clock') or 0)
      for row in source:
        if saves.clock_seconds(row.get('clock')) < cut:
          rows.append(dict(row))
      source = item.get('touches') or []
    rows.extend(dict(row) for row in source)
    return rows

  def request_scrub(self, seconds):
    """Ask the match loop to show this match clock and hold there."""
    try:
      target = int(seconds)
    except (TypeError, ValueError):
      return
    if target < 0 or target > 200 * 60:
      return
    with self._lock:
      self._scrub_to = target
      self._scrub_generation += 1

  def take_scrub(self):
    """The latest clock the overlay asked to show. None if it has not changed."""
    with self._lock:
      if self._scrub_generation == self._scrub_applied:
        return None
      self._scrub_applied = self._scrub_generation
      return self._scrub_to

  def scene(self):
    """Boxes, lines, and hiding to put back after a snapshot restore."""
    with self._lock:
      return {
          'boxes': list(self._boxes or []),
          'players': list(self._hidden_players),
          'ball': bool(self._hidden_ball),
          'lines': list(self._lines),
          'callouts': bool(self._callouts),
      }

  def hold_picture(self):
    """Stay on this frame until Resume. The engine hold is set by the caller."""
    with self._lock:
      self._frozen = True
      self._frozen_generation += 1
      self._frozen_applied = self._frozen_generation

  def release_picture(self):
    """Play again. A queued freeze from the hold does not win."""
    with self._lock:
      self._frozen = False
      self._frozen_generation += 1
      self._frozen_applied = self._frozen_generation

  def land_log(self, clock):
    """Present-tense chat follows the moment now on screen."""
    seconds = saves.clock_seconds(clock)
    with self._lock:
      future = self._future or []
      kept = []
      for row in future:
        if not isinstance(row, dict):
          continue
        if saves.clock_seconds(row.get('clock')) > seconds:
          continue
        try:
          kept.append({
              'team': int(row['team']),
              'shirt': int(row['shirt']),
              'action': str(row.get('action') or ''),
              'clock': str(row.get('clock') or ''),
          })
        except (KeyError, TypeError, ValueError):
          continue
      if len(kept) > 2000:
        kept = kept[-2000:]
      self._log = kept
      self._log_seen = set()
      self._played_until = seconds

  def saved_feed(self):
    """The full touch list once the clock has been moved. None before that."""
    with self._lock:
      if self._played_until is None or self._future is None:
        return None
      return self._future

  def set_viewing(self, on):
    with self._lock:
      self._viewing = bool(on)

  def viewing(self):
    with self._lock:
      return self._viewing

  def take_restart(self):
    """True once for each restart the overlay asked for."""
    with self._lock:
      if self._restart_generation == self._restart_applied:
        return False
      self._restart_applied = self._restart_generation
      return True

  def set_callouts(self, on):
    with self._lock:
      self._callouts = bool(on)
      self._callouts_generation += 1

  def take_callouts(self):
    """The next label switch. None if the overlay has not changed it."""
    with self._lock:
      if self._callouts_generation == self._callouts_applied:
        return None
      self._callouts_applied = self._callouts_generation
      return self._callouts

  def set_menu(self, on):
    with self._lock:
      self._menu = bool(on)
      self._menu_generation += 1

  def take_menu(self):
    """The next menu switch. None if the overlay has not changed it."""
    with self._lock:
      if self._menu_generation == self._menu_applied:
        return None
      self._menu_applied = self._menu_generation
      return self._menu

  def remember(self, status):
    """Keep this frame's touches and players for the match chat."""
    with self._lock:
      if self._played_until is not None and self._future is not None:
        seconds = saves.clock_seconds(status.get('clock'))
        kept = []
        for row in self._future:
          if not isinstance(row, dict):
            continue
          if saves.clock_seconds(row.get('clock')) > seconds:
            continue
          try:
            kept.append({
                'team': int(row['team']),
                'shirt': int(row['shirt']),
                'action': str(row.get('action') or ''),
                'clock': str(row.get('clock') or ''),
            })
          except (KeyError, TypeError, ValueError):
            continue
        if len(kept) > 2000:
          kept = kept[-2000:]
        self._log = kept
        self._played_until = seconds
      else:
        for team, key in ((0, 'left'), (1, 'right')):
          fresh = []
          for line in status.get(key) or []:
            if line.get('id') in self._log_seen:
              continue
            fresh.append(line)
          for line in reversed(fresh):
            self._log_seen.add(line.get('id'))
            self._log.append({
                'team': team,
                'shirt': int(line['shirt']),
                'action': str(line['action']),
                'clock': str(line['clock']),
            })
        if len(self._log) > 2000:
          self._log = self._log[-2000:]
      self._roster = list(status.get('roster') or [])
      self._ball = status.get('ball_meters')
      self._chat_view = {
          'score': list(status.get('score') or [0, 0]),
          'clock': status.get('clock') or '00:00',
          'speed': status.get('speed'),
          'left_name': status.get('left_name') or '',
          'right_name': status.get('right_name') or '',
      }

  def reset_match_log(self):
    """A new kickoff starts a new touch log and a new chat."""
    with self._lock:
      self._log = []
      self._log_seen = set()
      self._future = None
      self._chat_history = []
      self._roster = []
      self._hidden_players = []
      self._hidden_ball = False
      self._hidden_generation += 1
      self._lines = []
      self._lines_generation += 1
      self._timeline = []
      self._span = 0
      self._played_until = None
      self._branches = []
      self._moments = {}
      self._line_id = None
      self._sim_id = ''
      self._saved = None
      self._branch_applied = self._branch_generation
      self._formation_applied = self._formation_generation
      self._base_formation = None
      self._line_applied = self._line_generation
      self._scrub_applied = self._scrub_generation
    self.send(1, json.dumps({'kind': 'chat', 'reset': True}).encode('utf-8'))

  def take_boxes(self):
    """The next wire-box list. None if the chat has not asked."""
    with self._lock:
      if self._boxes_generation == self._boxes_applied:
        return None
      self._boxes_applied = self._boxes_generation
      return list(self._boxes or [])

  def take_hidden(self):
    """The next hidden players and ball. None if the chat has not asked."""
    with self._lock:
      if self._hidden_generation == self._hidden_applied:
        return None
      self._hidden_applied = self._hidden_generation
      return {
          'players': list(self._hidden_players),
          'ball': bool(self._hidden_ball),
      }

  def take_lines(self):
    """The next lines between players. None if the chat has not asked."""
    with self._lock:
      if self._lines_generation == self._lines_applied:
        return None
      self._lines_applied = self._lines_generation
      return list(self._lines)

  def ask(self, text, request_id):
    """Answer one question off the match thread."""
    question = str(text or '').strip()
    if not question:
      return
    if len(question) > 400:
      question = question[:400]
    with self._lock:
      if self._menu:
        return
      if self._chat_busy:
        busy = True
        snapshot = None
        history = None
      else:
        busy = False
        self._chat_busy = True
        snapshot = self._chat_snapshot()
        history = list(self._chat_history)
    if busy:
      self.send(1, json.dumps({
          'kind': 'chat',
          'id': request_id,
          'text': 'Still reading the log.',
      }).encode('utf-8'))
      return
    threading.Thread(
        target=self._answer,
        args=(question, request_id, snapshot, history),
        daemon=True).start()

  def _chat_snapshot(self):
    """Caller holds the match lock."""
    counts = match_chat.touch_counts(self._log)
    roster = []
    for player in self._roster:
      row = dict(player)
      row['touches'] = int(counts.get((row['team'], row['shirt']), 0))
      roster.append(row)
    view = self._chat_view
    return {
        'score': list(view.get('score') or [0, 0]),
        'clock': view.get('clock') or '00:00',
        'speed': view.get('speed'),
        'left_name': view.get('left_name') or '',
        'right_name': view.get('right_name') or '',
        'roster': roster,
        'log': list(self._log),
        'ball': self._ball,
        'hidden': {
            'players': list(self._hidden_players),
            'ball': bool(self._hidden_ball),
        },
        'captions': bool(self._callouts),
        'lines': list(self._lines),
        'future': None if self._future is None else list(self._future),
    }

  def _answer(self, question, request_id, snapshot, history):
    marks = None
    camera = None
    hidden = None
    captions = None
    lines = None
    moment_rows = None
    stored_moments = None
    stored_sim = ''
    found = match_chat.key_moments_from_question(question, snapshot)
    if found is not None:
      text, moment_rows = found
      ok = True
    else:
      formed = match_chat.formation_from_question(question, snapshot)
      if formed is not None:
        text = formed['text']
        if formed.get('sides'):
          if self.can_branch():
            self.request_formation(formed['sides'])
          else:
            text = 'Open a simulation first.'
        ok = True
      else:
        try:
          text, marks, camera, hidden, captions, lines = match_chat.answer(
              question, snapshot, history)
          ok = True
        except match_chat.MatchChatError as error:
          text = str(error)
          ok = False
        except Exception:
          text = 'Phi-4 mini did not answer.'
          ok = False
    with self._lock:
      self._chat_busy = False
      if ok:
        self._chat_history.append({'role': 'user', 'text': question})
        self._chat_history.append({'role': 'assistant', 'text': text})
        self._chat_history = self._chat_history[-6:]
      if marks is not None:
        self._boxes = marks
        self._boxes_generation += 1
      if hidden is not None:
        self._hidden_players = list(hidden.get('players') or [])
        self._hidden_ball = bool(hidden.get('ball'))
        self._hidden_generation += 1
      if captions is not None:
        self._callouts = bool(captions)
        self._callouts_generation += 1
      if lines is not None:
        self._lines = list(lines)
        self._lines_generation += 1
      if moment_rows is not None:
        # The question was about the timeline on screen.
        key = self._line_id or ''
        clean = saves._clean_moment_rows(moment_rows)
        if clean:
          self._moments[key] = clean
        else:
          self._moments.pop(key, None)
        stored_moments = {
            item_key: [dict(item) for item in item_rows]
            for item_key, item_rows in self._moments.items()
        }
        stored_sim = self._sim_id
    if stored_moments is not None and stored_sim:
      try:
        saves.write_moments(stored_sim, stored_moments)
      except OSError as error:
        print('Key moments were not saved: %s' % error, flush=True)
    if camera:
      self.set_camera(camera)
    self.send(1, json.dumps({
        'kind': 'chat',
        'id': request_id,
        'text': text,
    }).encode('utf-8'))

  def request_quit(self):
    """Ask the match loop to close the window."""
    with self._lock:
      self._quit = True

  def quit_requested(self):
    with self._lock:
      return self._quit

  def note_engine_frozen(self, frozen):
    """Record a freeze that the match window itself changed, such as F."""
    with self._lock:
      if self._frozen_generation != self._frozen_applied:
        return
      self._frozen = bool(frozen)

  def attached(self):
    with self._lock:
      return self._connection is not None

  def send(self, opcode, payload):
    """Write one frame. The match lock is not held during the write, so a
    full network buffer cannot block key input."""
    with self._lock:
      writer = self._writer
    if writer is None:
      return
    frame = _ws_frame(opcode, payload)
    with self._send_lock:
      with self._lock:
        if self._writer is not writer:
          return
      try:
        writer.write(frame)
        writer.flush()
      except (OSError, BrokenPipeError, ConnectionResetError, ValueError):
        with self._lock:
          if self._writer is writer:
            self._writer = None
            self._connection = None
            self._keys = set()
        return

  def publish(self, jpeg, status):
    with self._frame:
      self._jpeg = jpeg
      self._status = status
      self._sequence += 1
      self._frame.notify_all()

  def latest(self):
    with self._frame:
      return self._sequence, self._jpeg, dict(self._status)

  def wait_for_frame(self, seen):
    with self._frame:
      while self._sequence == seen:
        self._frame.wait()
      return self._sequence, self._jpeg

  def wait_for_status(self, seen):
    with self._frame:
      while self._sequence == seen:
        self._frame.wait()
      return self._sequence, dict(self._status)


def _ws_frame(opcode, payload):
  header = bytearray([0x80 | opcode])
  size = len(payload)
  if size < 126:
    header.append(size)
  elif size < 65536:
    header.append(126)
    header.extend(struct.pack('!H', size))
  else:
    header.append(127)
    header.extend(struct.pack('!Q', size))
  return bytes(header) + payload


def _read_exact(stream, size):
  chunks = []
  remaining = size
  while remaining:
    chunk = stream.read(remaining)
    if not chunk:
      raise ConnectionError('browser closed the match')
    chunks.append(chunk)
    remaining -= len(chunk)
  return b''.join(chunks)


def _read_client_frame(stream):
  header = _read_exact(stream, 2)
  opcode = header[0] & 0x0F
  masked = header[1] & 0x80
  size = header[1] & 0x7F
  if size == 126:
    size = struct.unpack('!H', _read_exact(stream, 2))[0]
  elif size == 127:
    size = struct.unpack('!Q', _read_exact(stream, 8))[0]
  if size > 1000000:
    raise ConnectionError('control message is too large')
  mask = _read_exact(stream, 4) if masked else b''
  payload = _read_exact(stream, size)
  if mask:
    payload = bytes(byte ^ mask[index & 3] for index, byte in enumerate(payload))
  return opcode, payload


def _accept_key(key):
  digest = hashlib.sha1(key.encode('ascii') + WS_GUID).digest()
  return base64.b64encode(digest).decode('ascii')


def encode_jpeg(frame, quality=90):
  # The engine frame is red, green, blue. The JPEG writer reads blue, green,
  # red. Leaving that as-is trades red and blue, so a yellow kit is sent to
  # the page as cyan and skin comes out cold.
  # 4:4:4 keeps the kit colors on the pixel they were drawn on. The default
  # 4:2:0 sample throws those colors away and the picture looks soft.
  ok, encoded = cv2.imencode('.jpg', cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), [
      int(cv2.IMWRITE_JPEG_QUALITY), int(quality),
      int(cv2.IMWRITE_JPEG_SAMPLING_FACTOR),
      int(cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444),
  ])
  if not ok:
    raise RuntimeError('Could not encode the match frame')
  return encoded.tobytes()


def advance(env):
  """Draw the next physics frame. The engine controls every player."""
  env._env.step()
  env._retrieve_observation()
  observation = env._observation
  done = env._step >= env._env.config.game_duration
  return observation, done


def redraw(env):
  """Draw the current moment again. This does not advance the match."""
  env._env.render(True)
  env._retrieve_observation()
  return env._observation


ROLE_NAMES = ['GK', 'CB', 'LB', 'RB', 'DM', 'CM', 'LM', 'RM', 'AM', 'CF']


def roster(observation):
  """Active players in the same order the engine camera uses."""
  players = []
  for team, side, label in ((0, 'left', 'Left'), (1, 'right', 'Right')):
    roles = observation['%s_team_roles' % side]
    active = observation['%s_team_active' % side]
    for index, role in enumerate(roles):
      if not active[index]:
        continue
      role_index = int(role)
      if 0 <= role_index < len(ROLE_NAMES):
        role_name = ROLE_NAMES[role_index]
      else:
        role_name = str(role_index)
      players.append({
          'team': team,
          'player': index,
          'name': '%s %d %s' % (label, index + 1, role_name),
      })
  return players


def _bounded(value, low, high, fallback):
  try:
    number = float(value)
  except (TypeError, ValueError):
    return fallback
  if number != number or number == float('inf') or number == float('-inf'):
    return fallback
  if number < low:
    return low
  if number > high:
    return high
  return number


def use_camera(env, live):
  team, player, lens, x, y, z, yaw, pitch = live.camera()
  config = env._env.game_config
  config.camera_team = team
  config.camera_player = player
  config.camera_lens = lens
  if lens == 3:
    config.camera_x = x
    config.camera_y = y
    config.camera_z = z
    config.camera_yaw = yaw
    config.camera_pitch = pitch


def match_status(observation, live):
  return {
      'game_mode': int(observation['game_mode']),
      'score': [int(observation['score'][0]), int(observation['score'][1])],
      'steps_left': int(observation['steps_left']),
      'players': roster(observation),
      'view': {
          'team': live.camera()[0],
          'player': live.camera()[1],
          'lens': live.camera()[2],
      },
      'frozen': live.frozen(),
  }


def window_is_hidden():
  return os.environ.get('BRANCHPLAY_HIDE_WINDOW') == '1'


def begin_match():
  if window_is_hidden():
    os.environ['BRANCHPLAY_HIDE_WINDOW'] = '1'
  configuration = football_config.Config({
      'level': '11_vs_11_stochastic',
      'players': [],
      'action_set': 'full',
      'real_time': False,
      'physics_steps_per_frame': 1,
      'render_resolution_x': 1280,
      'render_resolution_y': 720,
      'dump_full_episodes': False,
      'dump_scores': False,
  })
  env = football_env_core.FootballEnvCore(configuration)
  if not window_is_hidden():
    # A ball touch is named above the player on the menu and in a chosen
    # simulation. The menu itself does not take wire-box clicks. The camera
    # is the action view before the first frame, while the window is still
    # hidden.
    env._env.set_action_labels(True)
    env._env.set_menu_screen(True)
    env._env.game_config.camera_team = -1
    env._env.game_config.camera_player = 0
    env._env.game_config.camera_lens = 2
  env.render('rgb_array')
  env.reset()
  if not window_is_hidden():
    env._env.game_config.camera_team = -1
    env._env.game_config.camera_player = 0
    env._env.game_config.camera_lens = 2
  env._env.config.game_duration = FULL_MATCH_FRAMES
  env._retrieve_observation()
  return env, configuration


def run_match(env, configuration, live):
  """Step the engine on the main thread and publish every drawn frame."""
  while not live.attached():
    time.sleep(0.05)
  observation = env.observation()
  live.publish(
      encode_jpeg(observation['frame']),
      match_status(observation, live))
  next_tick = time.perf_counter()
  reported = next_tick
  drawn = 0
  shown_camera = live.camera()
  holding = False
  try:
    while True:
      use_camera(env, live)
      if live.frozen():
        # Leave the players, the ball, and the clock where they are.
        # A camera change only redraws this same moment.
        camera = live.camera()
        changed = camera != shown_camera
        if changed:
          observation = redraw(env)
          shown_camera = camera
        if not holding or changed:
          live.publish(encode_jpeg(observation['frame']),
                       match_status(observation, live))
        holding = True
        next_tick = time.perf_counter()
        # A free camera is being dragged, so pick up the next pose quickly.
        time.sleep(0.016 if camera[2] == 3 else 0.05)
        continue
      holding = False
      observation, done = advance(env)
      live.publish(encode_jpeg(observation['frame']),
                   match_status(observation, live))
      shown_camera = live.camera()
      drawn += 1
      if done:
        env.reset()
        env._env.config.game_duration = FULL_MATCH_FRAMES
      now = time.perf_counter()
      if now - reported >= 10:
        print('Match %.0f pictures/sec' % (drawn / (now - reported)), flush=True)
        reported = now
        drawn = 0
      next_tick += PHYSICS_FRAME_SECONDS
      remaining = next_tick - time.perf_counter()
      if remaining > 0:
        time.sleep(remaining)
      else:
        next_tick = time.perf_counter()
  finally:
    env.close()


def pump_status(live):
  """Send match state. The overlay does not receive pictures."""
  seen = 0
  while True:
    seen, status = live.wait_for_status(seen)
    if not status:
      continue
    try:
      live.send(1, json.dumps(status).encode('utf-8'))
    except Exception:
      continue


def pump_frames(live):
  """Send the newest frame. A closed browser must not stop later pictures."""
  seen = 0
  while True:
    seen, jpeg = live.wait_for_frame(seen)
    if jpeg is None:
      continue
    try:
      live.send(2, jpeg)
    except Exception:
      continue


UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui', 'dist')

CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.json': 'application/json',
    '.map': 'application/json',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
}


def _static_file(url_path):
  if url_path == '/':
    url_path = '/index.html'
  root = os.path.realpath(UI_DIR)
  full = os.path.realpath(os.path.join(root, url_path.lstrip('/')))
  if full != root and not full.startswith(root + os.sep):
    return None
  if not os.path.isfile(full):
    return None
  return full


def _delete_clip(path):
  if not path:
    return
  try:
    os.remove(path)
  except OSError:
    pass


def _send_clip(handler, live, name):
  """Send the key-moment video, including a range so the player can start."""
  path = live.clip_file(name)
  if path is None:
    handler.send_error(404)
    return
  try:
    size = os.path.getsize(path)
  except OSError:
    handler.send_error(404)
    return
  media = _clip_media_type(path)
  if media.startswith('image/'):
    try:
      with open(path, 'rb') as handle:
        body = handle.read()
    except OSError:
      handler.send_error(404)
      return
    handler.send_response(200)
    handler.send_header('Content-Type', media)
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    try:
      handler.wfile.write(body)
    except (ConnectionError, OSError):
      return
    return
  start = 0
  end = size - 1
  status = 200
  range_header = handler.headers.get('Range', '')
  if range_header.startswith('bytes='):
    spec = range_header[6:].split(',', 1)[0].strip()
    left, _, right = spec.partition('-')
    try:
      if left == '' and right:
        length = int(right)
        start = max(0, size - length)
      elif left:
        start = int(left)
        end = int(right) if right else size - 1
    except ValueError:
      start, end = 0, size - 1
    if start < 0 or start >= size or end < start:
      handler.send_response(416)
      handler.send_header('Content-Range', 'bytes */%d' % size)
      handler.send_header('Content-Length', '0')
      handler.end_headers()
      return
    end = min(end, size - 1)
    status = 206
  length = end - start + 1
  try:
    with open(path, 'rb') as handle:
      handle.seek(start)
      body = handle.read(length)
  except OSError:
    handler.send_error(404)
    return
  handler.send_response(status)
  handler.send_header('Content-Type', media)
  handler.send_header('Accept-Ranges', 'bytes')
  handler.send_header('Content-Length', str(len(body)))
  if status == 206:
    handler.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
  handler.send_header('Cache-Control', 'no-store')
  handler.end_headers()
  try:
    handler.wfile.write(body)
  except (ConnectionError, OSError):
    return


def make_handler(live, use_overlay=False):

  class Handler(BaseHTTPRequestHandler):

    protocol_version = 'HTTP/1.1'

    def do_GET(self):
      path = self.path.split('?', 1)[0]
      if path.startswith('/clips/'):
        _send_clip(self, live, path[len('/clips/'):])
        return
      if use_overlay and path != '/session' and path != '/state':
        full = _static_file(path)
        if full is None:
          self.send_error(404)
          return
        with open(full, 'rb') as handle:
          body = handle.read()
        kind = CONTENT_TYPES.get(os.path.splitext(full)[1], 'application/octet-stream')
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)
        return
      if path in ('/', '/index.html'):
        body = page_html().encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)
        return
      if path == '/state':
        _, _, status = live.latest()
        body = json.dumps(status).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)
        return
      if path != '/session':
        self.send_error(404)
        return
      self._play()

    def _play(self):
      key = self.headers.get('Sec-WebSocket-Key')
      if not key or self.headers.get('Upgrade', '').lower() != 'websocket':
        self.send_error(400)
        return
      self.send_response(101, 'Switching Protocols')
      self.send_header('Upgrade', 'websocket')
      self.send_header('Connection', 'Upgrade')
      self.close_connection = True
      self.send_header('Sec-WebSocket-Accept', _accept_key(key))
      self.end_headers()
      self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
      generation = live.attach(self.connection, self.wfile)
      try:
        while True:
          opcode, payload = _read_client_frame(self.rfile)
          if opcode == 8:
            break
          if opcode == 9:
            live.send(10, payload)
            continue
          if opcode != 1:
            continue
          try:
            message = json.loads(payload.decode('utf-8'))
          except (UnicodeDecodeError, json.JSONDecodeError):
            continue
          names = message.get('keys', None)
          if isinstance(names, list):
            live.set_keys(str(name) for name in names)
          camera = message.get('camera', None)
          if isinstance(camera, dict):
            live.set_camera(camera)
          edit = message.get('edit')
          if edit in ('on', 'off', 'commit', 'play', 'remove', 'dismiss'):
            live.request_edit(edit)
          elif edit == 'add':
            try:
              team = int(message.get('team'))
            except (TypeError, ValueError):
              team = -1
            if team in (0, 1):
              live.request_edit('add', team)
            else:
              live.request_edit('dismiss')
          elif 'frozen' in message:
            live.set_frozen(message.get('frozen'))
          if 'fullscreen' in message:
            live.set_fullscreen(message.get('fullscreen'))
          if 'strip' in message:
            live.set_bottom_band(message.get('strip'))
          if message.get('restart'):
            live.request_restart()
          if message.get('simulate'):
            live.request_simulate(bool(message.get('deterministic')))
          if message.get('clear_branches'):
            live.request_clear_branches()
          branch = message.get('branch')
          if isinstance(branch, dict):
            live.request_branch(
                branch.get('count'), branch.get('minutes'), branch.get('clock'),
                branch.get('seconds'))
          brief = message.get('brief')
          if isinstance(brief, dict):
            live.request_brief(
                brief.get('start'), brief.get('end'), brief.get('id'),
                brief.get('language'))
          if message.get('brief_stop'):
            live.request_brief_stop()
          moment = message.get('moment')
          if isinstance(moment, dict):
            live.request_moment(
                moment.get('start'), moment.get('end'), moment.get('id'),
                moment.get('language'))
          if message.get('moment_stop'):
            live.request_moment_stop()
          if message.get('clip_done'):
            live.finish_clip()
          if message.get('compare'):
            live.request_compare()
          if 'line' in message:
            live.request_line(message.get('line'))
          if 'scrub' in message:
            live.request_scrub(message.get('scrub'))
          opened = message.get('open')
          if isinstance(opened, str) and opened:
            live.request_open(opened)
          removed = message.get('remove_simulation')
          if isinstance(removed, str) and removed:
            live.request_remove_simulation(removed)
          if 'callouts' in message:
            live.set_callouts(message.get('callouts'))
          if 'menu' in message:
            live.set_menu(message.get('menu'))
          if message.get('home'):
            live.request_home()
          if message.get('quit'):
            live.request_quit()
          ask = message.get('ask')
          if isinstance(ask, str):
            live.ask(ask, message.get('id'))
      except (ConnectionError, OSError, ValueError):
        return
      finally:
        live.detach(generation)

    def log_message(self, format, *args):
      return

  return Handler


def page_html():
  return PAGE


def _window_camera(env):
  config = env._env.game_config
  return (
      int(config.camera_team),
      int(config.camera_player),
      int(config.camera_lens),
      float(config.camera_x),
      float(config.camera_y),
      float(config.camera_z),
      float(config.camera_yaw),
      float(config.camera_pitch),
  )


_FEED_IDS = {'left': [], 'right': [], 'next': 1}


def _same_touch(row, line):
  return (row['shirt'] == line['shirt'] and row['action'] == line['action']
          and row['clock'] == line['clock'])


def _feed_from_saved(rows, clock):
  """The latest saved touches at or before this clock, for the touch panel.

  Ids stay the row's place in the saved list, so a status tick does not
  treat the same touch as new.
  """
  now = saves.clock_seconds(clock)
  left = []
  for index, row in enumerate(rows or []):
    if not isinstance(row, dict):
      continue
    if saves.clock_seconds(row.get('clock')) > now:
      continue
    try:
      left.append({
          'shirt': int(row.get('shirt') or 0),
          'action': str(row.get('action') or ''),
          'clock': str(row.get('clock') or ''),
          'id': index + 1,
      })
    except (TypeError, ValueError):
      continue
  return left[-8:], []


def _feed_lines(feed, key):
  """Stamp a stable id on each touch so a new row can animate in place.

  New touches are inserted at the front and the list keeps eight. A row that
  is still here keeps the id it had last time.
  """
  incoming = []
  for row in feed[key]:
    incoming.append({
        'shirt': int(row['shirt']),
        'action': str(row['action']),
        'clock': str(row['clock']),
    })
  previous = _FEED_IDS[key]
  matched = 0
  limit = min(len(incoming), len(previous))
  for count in range(limit, 0, -1):
    start = len(incoming) - count
    if all(_same_touch(previous[index], incoming[start + index])
           for index in range(count)):
      matched = count
      break
  new_count = len(incoming) - matched
  stamped = []
  for index, line in enumerate(incoming):
    if index < new_count:
      line['id'] = _FEED_IDS['next']
      _FEED_IDS['next'] += 1
    else:
      line['id'] = previous[index - new_count]['id']
    stamped.append(line)
  _FEED_IDS[key] = stamped
  return stamped


_ROLE_NAMES = ('GK', 'CB', 'LB', 'RB', 'DM', 'CM', 'LM', 'RM', 'AM', 'CF')


def _roster(env, info, listed):
  """Roles, places, and speeds for the match chat. Team 1 is unmirrored."""
  steps = int(env._env.game_config.physics_steps_per_frame) or 10
  owned_team = int(info.ball_owned_team)
  owned_player = int(info.ball_owned_player)
  meta = {}
  for row in listed:
    meta[(row['team'], row['player'])] = row
  roster = []
  sides = (info.left_team, info.right_team)
  for team, players in enumerate(sides):
    for index in range(len(players)):
      player = players[index]
      row = meta.get((team, index), {})
      x = float(player.position[0])
      y = float(player.position[1])
      if team == 1:
        x = -x
        y = -y
      dx = float(player.direction[0])
      dy = float(player.direction[1])
      speed = ((dx * dx + dy * dy) ** 0.5) * steps
      role_index = int(player.role)
      if 0 <= role_index < len(_ROLE_NAMES):
        role = _ROLE_NAMES[role_index]
      else:
        role = 'unknown'
      roster.append({
          'team': team,
          'player': index,
          'name': str(row.get('surname') or ''),
          'shirt': int(row.get('shirt') or 0),
          'role': role,
          'x': round(x, 1),
          'y': round(y, 1),
          'speed': round(speed, 1),
          'tired': round(float(player.tired_factor), 2),
          'active': bool(player.is_active),
          'ball': owned_team == team and owned_player == index,
          'touches': 0,
      })
  return roster


_POSSESSION_CACHE = {'key': None, 'share': [50, 50]}


def _possession_share(rows, clock):
  """Percent of time each team has had the ball, up to this clock.

  The gap from one touch to the next belongs to the team that touched the
  ball. The last of those touches holds through the clock on screen. With
  no touches yet, the split is even. Touches later than the clock are left
  out, so a scrub shows the share at the moment on screen.
  """
  now = saves.clock_seconds(clock)
  count = 0 if not rows else len(rows)
  key = (id(rows), count, now)
  if key == _POSSESSION_CACHE['key']:
    return _POSSESSION_CACHE['share']
  events = []
  for index, row in enumerate(rows or []):
    if not isinstance(row, dict):
      continue
    try:
      team = int(row.get('team'))
    except (TypeError, ValueError):
      continue
    if team not in (0, 1):
      continue
    touched = saves.clock_seconds(row.get('clock'))
    if touched > now:
      continue
    events.append((touched, index, team))
  events.sort()
  held = [0, 0]
  for index, (touched, _order, team) in enumerate(events):
    end = events[index + 1][0] if index + 1 < len(events) else now
    if end > touched:
      held[team] += end - touched
  total = held[0] + held[1]
  if total <= 0:
    share = [50, 50]
  else:
    left = int(round(100.0 * held[0] / total))
    left = max(0, min(100, left))
    share = [left, 100 - left]
  _POSSESSION_CACHE['key'] = key
  _POSSESSION_CACHE['share'] = share
  return share


def _attach_possession(status, live):
  """Add each team's share of the ball. The menu has no score card."""
  if not live.viewing():
    status['possession'] = [50, 50]
    return
  status['possession'] = live.possession(status.get('clock'))


def window_status(env, frozen):
  """State for the overlay. This does not read the picture back."""
  info = env._env.get_info()
  feed = env._env.hud_feed()
  camera = _window_camera(env)
  listed = []
  for row in feed['players']:
    listed.append({
        'team': int(row['team']),
        'player': int(row['player']),
        'name': str(row['name']),
        'surname': str(row.get('surname') or ''),
        'shirt': int(row.get('shirt') or 0),
    })
  players = [{
      'team': row['team'],
      'player': row['player'],
      'name': row['name'],
  } for row in listed]
  return {
      'score': [int(info.left_goals), int(info.right_goals)],
      'steps_left': int(env._env.config.game_duration - info.step),
      'players': players,
      'view': {
          'team': camera[0],
          'player': camera[1],
          'lens': camera[2],
      },
      'frozen': bool(frozen),
      'fullscreen': bool(env._env.fullscreen()),
      'speed': round(float(feed['speed']), 1),
      'clock': str(feed['clock']),
      'left_name': str(feed['left_name']),
      'right_name': str(feed['right_name']),
      'left': _feed_lines(feed, 'left'),
      'right': _feed_lines(feed, 'right'),
      'dots': _pitch_dots(feed),
      'add_prompt': _add_prompt_pending(env),
      'ball': _pitch_ball(feed),
      'callouts': _callouts(feed),
      'roster': _roster(env, info, listed),
      'ball_meters': [
          round(float(info.ball_position[0]), 1),
          round(float(info.ball_position[1]), 1),
      ],
  }


def _pitch_dots(feed):
  dots = []
  for row in feed.get('dots', []):
    dots.append({
        'team': int(row['team']),
        'x': float(row['x']),
        'y': float(row['y']),
        'r': int(row['r']),
        'g': int(row['g']),
        'b': int(row['b']),
    })
  return dots


def _callouts(feed):
  rows = []
  for row in feed.get('callouts') or []:
    text = str(row.get('text', '')).strip()
    if not text:
      continue
    rows.append({
        'text': text,
        'x': float(row.get('x', 0.0)),
        'y': float(row.get('y', 0.0)),
    })
  return rows


def _pitch_ball(feed):
  if feed.get('ball_hidden'):
    return None
  ball = feed.get('ball') or {}
  return {
      'x': float(ball.get('x', 0.5)),
      'y': float(ball.get('y', 0.5)),
  }


def _apply_overlay_camera(env, choice):
  team, player, lens = choice
  config = env._env.game_config
  config.camera_team = int(team)
  config.camera_player = int(player)
  config.camera_lens = int(lens)


def _note_escape(env, live):
  """Escape, from the match window or the panel, asks to return to the menu."""
  try:
    if env._env.take_escape():
      live.request_home()
  except AttributeError:
    pass
  return live.home_pending()


def _return_to_menu(env, live):
  """Leave the simulation and show the menu over a fresh match."""
  live.request_moment_stop()
  live.set_viewing(False)
  live.set_menu(True)
  live.set_frozen(False)
  try:
    env._env.set_held(False)
  except AttributeError:
    pass
  _restart_window_match(env, live)
  env._env.set_menu_screen(True)
  env._env.set_action_labels(True)
  config = env._env.game_config
  config.camera_team = -1
  config.camera_player = 0
  config.camera_lens = 2
  config.camera_fov = 0.0
  config.camera_focus = 0.0
  live.set_camera({'team': -1, 'player': 0, 'lens': 2})
  env._env.render(True)
  status = window_status(env, False)
  status['phase'] = 'menu'
  status['simulations'] = saves.list_simulations()
  live.publish(None, status)


def _restart_window_match(env, live):
  """Start the next match without reading the picture.

  The gym reset reads a 1280 by 720 frame. A resized or fullscreen window is
  larger than that, so the read crashes. The match is still built with drawing
  on. That is what loads the stadium around the pitch. A rebuild with drawing
  off keeps only the pitch. The warmup steps are the part that skip the picture.
  """
  _finish_edit(env, live, False)
  live.reset_match_log()
  showing = bool(env._env.game_config.render)
  env._reset(True, inc=1)
  env._env.game_config.render = False
  try:
    while not env._retrieve_observation():
      env._env.step()
  finally:
    env._env.game_config.render = showing
  env._env.config.game_duration = FULL_MATCH_FRAMES


def _branch_bounds(count, minutes):
  """How many branches, and how many match minutes. None runs to the end."""
  try:
    count = int(count)
  except (TypeError, ValueError):
    count = 2
  count = max(1, min(4, count))
  if minutes in (None, '', 0, '0'):
    return count, None
  try:
    minutes = int(minutes)
  except (TypeError, ValueError):
    return count, None
  if minutes <= 0:
    return count, None
  return count, max(1, min(90, minutes))


def _branch_seed(base, index, clock):
  """A seed that is not the one this moment was already using."""
  origin = int(base) & 0x7FFFFFFF
  seed = (origin + 10007 * (int(index) + 1) + int(clock) * 17) & 0x7FFFFFFF
  if seed == 0 or seed == origin:
    seed = (seed + 1) & 0x7FFFFFFF
  return seed


def _reset_for_sim(env, deterministic):
  """Start the scenario, then fix the seed when the match should repeat.

  A stochastic start keeps the scenario's own random seed. A deterministic
  start uses episode 0 and seed 42, so the same kickoff can be played again.
  """
  game = env._env
  if deterministic:
    env._config['episode_number'] = 0
  env._state = football_env_core.EnvState()
  env._observation = None
  env._steps_time = 0
  env._step = 0
  env._config.NewScenario(inc=0 if deterministic else 1)
  if game.state == football_env_core.GameState.game_created:
    game.start_game()
  game.state = football_env_core.GameState.game_running
  scenario = env._config.ScenarioConfig()
  if deterministic:
    scenario.deterministic = True
    scenario.game_engine_random_seed = 42
    scenario.reverse_team_processing = False
  game.reset(scenario, True)


def _kickoff(env, live, deterministic=False):
  """Start a match and leave drawing off. The snapshot is the kickoff."""
  live.reset_match_log()
  env._env.set_menu_screen(True)
  _reset_for_sim(env, deterministic)
  env._env.game_config.render = False
  while not env._retrieve_observation():
    if live.quit_requested():
      return None
    env._env.step()
  env._env.config.game_duration = FULL_MATCH_FRAMES
  _remember_base_formation(env, live)
  return env.get_state({})


def _publish_progress(live, env, fraction):
  live.publish(None, {
      'phase': 'saving',
      'progress': round(max(0.0, min(1.0, fraction)), 4),
      'fullscreen': bool(env._env.fullscreen()),
      'simulations': saves.list_simulations(),
  })


def _begin_view(env, live, state, touches=None):
  """Restore a kickoff and hand the picture back to the match loop."""
  _restore_state(env, live, state)
  env._env.game_config.render = True
  env._env.set_action_labels(True)
  env._env.set_menu_screen(False)
  config = env._env.game_config
  config.camera_team = -1
  config.camera_player = 0
  config.camera_lens = 0
  live.set_camera({'team': -1, 'player': 0, 'lens': 0})
  live.set_frozen(False)
  live.set_callouts(True)
  live.set_menu(False)
  live.set_viewing(True)
  live.set_future(touches)
  env._env.render(True)
  env._env.clear_touches()
  _FEED_IDS['left'] = []
  _FEED_IDS['right'] = []
  _FEED_IDS['next'] = 1
  status = window_status(env, False)
  status['phase'] = 'view'
  _attach_possession(status, live)
  _attach_timeline(status, live)
  live.publish(None, status)


def _attach_timeline(status, live):
  status['span'] = live.span()
  status['length'] = live.base_span()
  status['branches'] = live.branch_menu()
  status['branch'] = live.line_id()
  status['moments'] = live.moments()
  status['line_moments'] = live.moment_map()
  status['simulations'] = saves.list_simulations()
  status['edit'] = live.edit_phase()
  brief = live.brief_view()
  if brief:
    status['brief'] = brief


def _touch_rows(env):
  touches = []
  for row in env._env.touch_log():
    touches.append({
        'team': int(row['team']),
        'shirt': int(row['shirt']),
        'name': str(row['name']),
        'action': str(row['action']),
        'clock': str(row['clock']),
        'x': float(row['x']),
        'y': float(row['y']),
        'speed': float(row['speed']),
        'ball_x': float(row['ball_x']),
        'ball_y': float(row['ball_y']),
        'ball_speed': float(row['ball_speed']),
    })
  return touches


def _simulate_and_save(env, live, deterministic=False):
  """Run one match without drawing, save the kickoff, then open that save."""
  started = time.perf_counter()
  state = _kickoff(env, live, deterministic)
  if state is None:
    return
  info = env._env.get_info()
  start = int(info.step)
  duration = int(env._env.config.game_duration)
  span = max(1, duration - start)
  marks = [{
      'step': start,
      'clock': saves.clock_from_step(start),
      'state': _state_blob(state),
  }]
  _publish_progress(live, env, 0.0)
  last_percent = 0
  guard = 0
  while int(env._env.get_info().step) < duration:
    if live.quit_requested():
      env._env.game_config.render = True
      return
    env._env.step()
    guard += 1
    if guard % 40 == 0:
      _note_minute(env, marks, duration)
    done = int(env._env.get_info().step) - start
    percent = min(100, int(max(0, done) * 100 / span))
    if percent != last_percent:
      last_percent = percent
      _publish_progress(live, env, percent / 100.0)
      env._env.poll_window(0.0)
    elif guard % 200 == 0:
      env._env.poll_window(0.0)
    if guard > span * 2:
      break
  info = env._env.get_info()
  feed = env._env.hud_feed()
  sim_id = time.strftime('%Y%m%d-%H%M%S')
  if os.path.exists(os.path.join(saves.directory(), '%s.state' % sim_id)):
    sim_id = '%s-%d' % (sim_id, int(time.time() * 1000) % 1000)
  touches = _touch_rows(env)
  saves.write_simulation(
      sim_id, state,
      str(feed['left_name']), str(feed['right_name']),
      [int(info.left_goals), int(info.right_goals)],
      touches, deterministic=deterministic)
  live.set_sim(sim_id)
  end_step = int(info.step)
  end_clock = saves.clock_from_step(end_step)
  try:
    saves.write_timeline(sim_id, marks, end_step, end_clock)
    live.set_timeline(marks, end_clock)
  except (OSError, struct.error, ValueError) as error:
    print('Timeline was not saved: %s' % error, flush=True)
  print('Saved simulation %s in %.1fs' % (sim_id, time.perf_counter() - started),
        flush=True)
  _publish_progress(live, env, 1.0)
  _begin_view(env, live, state, touches)


def _state_blob(state):
  if isinstance(state, (bytes, bytearray)):
    return bytes(state)
  return bytes(state)


def _add_prompt_pending(env):
  try:
    return bool(env._env.add_prompt_pending())
  except AttributeError:
    return False


def _added_players(env):
  """Bodies appended past the starting eleven, in team order."""
  try:
    rows = env._env.added_players()
  except AttributeError:
    return []
  kept = []
  for row in rows:
    try:
      team = int(row['team'])
      shirt = int(row['shirt'])
      role = int(row['role'])
      kept.append({
          'team': team,
          'name': str(row['name']),
          'shirt': shirt,
          'x': round(float(row['x']), 4),
          'y': round(float(row['y']), 4),
          'role': role,
      })
    except (TypeError, ValueError, KeyError):
      continue
  return kept


def _sync_added(env, roster):
  """Put the extra bodies back before a snapshot that includes them is read."""
  try:
    env._env.sync_added(roster or [])
  except AttributeError:
    return


def _restore_state(env, live, state):
  """Put a snapshot back. A stoppage is still a valid moment to return to."""
  _sync_added(env, live.line_added() if live is not None else [])
  env._env.config.game_duration = FULL_MATCH_FRAMES
  raw = env._env.set_state(_state_blob(state))
  try:
    env._retrieve_observation()
  except Exception:
    pass
  try:
    loaded = pickle.loads(raw)
    core = loaded.get('FootballEnvCore')
    if core is not None:
      env._state = core
  except Exception:
    pass


def _note_minute(env, marks, duration):
  """Keep one snapshot each time the match minute changes."""
  step = int(env._env.get_info().step)
  if step >= duration:
    return
  clock = saves.clock_from_step(step)
  if marks and marks[-1]['clock'] // 60 == clock // 60:
    return
  marks.append({
      'step': step,
      'clock': clock,
      'state': _state_blob(env.get_state({})),
  })


def _restore_scene(env, live):
  """Put the camera and the caption switch back.

  Wire boxes, connection lines, and hidden players live on the match, not in
  the snapshot. Writing the chat's copy over them drops a box that was added
  by clicking.
  """
  use_camera(env, live)
  env._env.set_action_labels(bool(live.scene()['callouts']))
  env._env.set_menu_screen(False)


def _scrub_to(env, live, seconds, force=False, present=True):
  """Show one moment of the saved match and hold the picture there."""
  if not live.viewing():
    return
  _finish_edit(env, live, True)
  span = live.span()
  if span <= 0:
    return
  target = max(0, min(int(seconds), int(span)))
  marks = live.marks_for(target)
  if not marks:
    return
  chosen = saves.pick_checkpoint(marks, target)
  showing = bool(env._env.game_config.render)
  duration = int(env._env.config.game_duration)
  try:
    current_step = int(env._env.get_info().step)
    target_step = saves.step_for_clock(target)
    restore = force or saves.scrub_plan(
        current_step, target_step, chosen['step']) == 'restore'
    env._env.game_config.render = False
    if restore:
      _restore_state(env, live, chosen['state'])
      env._env.clear_touches()
      _restore_scene(env, live)
      _FEED_IDS['left'] = []
      _FEED_IDS['right'] = []
    guard = 0
    while True:
      if live.quit_requested():
        return
      step = int(env._env.get_info().step)
      if target <= 0 or step >= target_step or step >= duration - 1:
        break
      env._env.step()
      guard += 1
      if guard % 20 == 0:
        env._env.poll_window(0.0)
      if guard > duration:
        break
  finally:
    env._env.game_config.render = showing
    env._env.set_held(True)
    live.hold_picture()
    _restore_scene(env, live)
    if present:
      env._env.render(True)
  live.land_log(env._env.hud_feed().get('clock'))


def _scoring_clock(rows, start, end):
  """The shot that leads to the goal, and the goal clock.

  The shot is the last SHOT at or before the goal inside the stretch.
  With no goal in the list, the stretch's own end is the goal clock.
  """
  start = int(start)
  end = int(end)
  goal = None
  shots = []
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    clock = saves.clock_seconds(row.get('clock'))
    if clock < start or clock > end:
      continue
    action = str(row.get('action') or '').upper()
    if action == 'SHOT':
      shots.append(clock)
    elif action in ('GOAL', 'OWN GOAL'):
      goal = clock
  if goal is None:
    goal = end
  shot = None
  for clock in shots:
    if clock <= goal:
      shot = clock
  return shot, goal


_PASSES = ('SHORT PASS', 'LONG PASS', 'HIGH PASS')


def _same_player(row, team, shirt):
  try:
    return int(row.get('team')) == int(team) and int(row.get('shirt')) == int(shirt)
  except (TypeError, ValueError):
    return False


def _assist_clock(rows, start, end):
  """The second before the pass that reaches the player who scores.

  That pass is the last short, long, or high pass by someone else after
  which the scorer is the next player on the ball. The hold is one match
  second before it, so the pass itself plays when the camera returns.
  """
  start = int(start)
  end = int(end)
  window = []
  scorer = None
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    clock = saves.clock_seconds(row.get('clock'))
    if clock < start or clock > end:
      continue
    window.append(row)
    action = str(row.get('action') or '').upper()
    if action in ('GOAL', 'OWN GOAL'):
      scorer = (row.get('team'), row.get('shirt'))
  if scorer is None or scorer[0] is None:
    return None
  assist = None
  for index, row in enumerate(window):
    action = str(row.get('action') or '').upper()
    if action not in _PASSES or _same_player(row, scorer[0], scorer[1]):
      continue
    receiver = None
    for later in window[index + 1:]:
      if _same_player(later, row.get('team'), row.get('shirt')):
        continue
      receiver = later
      break
    if receiver is not None and _same_player(receiver, scorer[0], scorer[1]):
      assist = saves.clock_seconds(row.get('clock'))
  if assist is None:
    return None
  return max(start, assist - 1)


def _moment_beats(rows, start, end):
  """When the scorer's name comes in, and where the scoring touch goes slow.

  The name comes in just before the pass to the scorer. Slow motion starts
  one match second before the shot and runs through the goal.
  """
  start = int(start)
  end = int(end)
  shot, goal = _scoring_clock(rows, start, end)
  slow_from = (shot - 1) if shot is not None else max(start, goal - 2)
  if slow_from < start:
    slow_from = start
  show = _assist_clock(rows, start, end)
  if show is None:
    show = shot if shot is not None else max(start, slow_from)
  if show < start:
    show = start
  return show, slow_from, goal


# At the foot. The body point sits a little off the ball even then, so a
# closest gap inside _SCORER_BODY also counts once the ball leaves it.
_SCORER_REACH = 0.2
_SCORER_BODY = 0.85


def _scorer_identity(rows, start, end):
  """Team and shirt of the player who scores inside this clip."""
  found = None
  start = int(start)
  end = int(end)
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    clock = saves.clock_seconds(row.get('clock'))
    if clock < start or clock > end:
      continue
    action = str(row.get('action') or '').upper()
    if action not in ('GOAL', 'OWN GOAL'):
      continue
    try:
      found = (int(row.get('team')), int(row.get('shirt')))
    except (TypeError, ValueError):
      continue
  return found


def _scoring_touch(clock, shot, gap, nearest):
  """Whether the ball is at the scorer now, and the closest gap so far.

  A gap of 0.2m is the ball on the player. The body point is often
  farther than that when the ball is already at the foot, so the closest
  gap in the shot window counts once the ball starts away from it. A gap
  that is still about a metre and still falling is the ball in flight.
  Returns (fire, nearest).
  """
  if shot is not None and clock < shot - 1:
    return False, nearest
  if gap is None:
    return False, nearest
  if gap <= _SCORER_REACH:
    return True, gap
  if nearest is None or gap < nearest:
    return False, gap
  if nearest <= _SCORER_BODY and gap >= nearest + 0.03:
    return True, nearest
  return False, nearest


def _lerp_angle(a, b, t):
  delta = (b - a + math.pi) % (2.0 * math.pi) - math.pi
  return a + delta * t


def _pose_delta(older, newer):
  """How far the camera moved, with yaw taking the short way around."""
  return (
      newer[0] - older[0],
      newer[1] - older[1],
      newer[2] - older[2],
      (newer[3] - older[3] + math.pi) % (2.0 * math.pi) - math.pi,
      newer[4] - older[4],
  )


def _step_pose(pose, velocity, dt):
  """Move a free-camera pose by one step and keep it inside the engine limits."""
  yaw = pose[3] + velocity[3] * dt
  yaw = yaw % (2.0 * math.pi)
  return (
      max(-100.0, min(100.0, pose[0] + velocity[0] * dt)),
      max(-80.0, min(80.0, pose[1] + velocity[1] * dt)),
      max(0.4, min(60.0, pose[2] + velocity[2] * dt)),
      yaw,
      max(-1.15, min(1.15, pose[4] + velocity[4] * dt)),
  )


def _mix_pose(origin, reveal, t):
  return (
      origin[0] + (reveal[0] - origin[0]) * t,
      origin[1] + (reveal[1] - origin[1]) * t,
      origin[2] + (reveal[2] - origin[2]) * t,
      _lerp_angle(origin[3], reveal[3], t),
      origin[4] + (reveal[4] - origin[4]) * t,
  )


def _aim_pose(x, y, z, aim_x, aim_y, aim_z):
  dx = aim_x - x
  dy = aim_y - y
  horizontal = math.hypot(dx, dy) or 0.001
  yaw = math.atan2(dy, dx)
  if yaw < 0.0:
    yaw += 2.0 * math.pi
  pitch = -math.atan2(z - aim_z, horizontal)
  return (
      max(-100.0, min(100.0, x)),
      max(-80.0, min(80.0, y)),
      max(0.4, min(60.0, z)),
      yaw,
      max(-1.55, min(1.15, pitch)),
  )


def _place_playback_window(env):
  """Resize the match window. Key-moment playback does not call this."""
  try:
    env._env.place_playback_window()
  except AttributeError:
    if env._env.fullscreen():
      env._env.set_fullscreen(False)
  env._env.poll_window(0.0)


def _restore_playback_window(env):
  try:
    env._env.restore_playback_window()
  except AttributeError:
    pass
  env._env.poll_window(0.0)


def _set_action_camera(env, live):
  live.set_camera({'team': -1, 'player': 0, 'lens': 2})
  use_camera(env, live)


def _restore_saved_camera(env, live, saved):
  live.set_camera({
      'team': saved[0],
      'player': saved[1],
      'lens': saved[2],
      'x': saved[3],
      'y': saved[4],
      'z': saved[5],
      'yaw': saved[6],
      'pitch': saved[7],
  })
  use_camera(env, live)


def _read_pose(env):
  try:
    pose = env._env.camera_pose()
    return tuple(float(pose[index]) for index in range(5))
  except (TypeError, ValueError, AttributeError, IndexError):
    return None


# The goal line. The net is 2.55m past it. Python's ball position is not in
# these meters: x is divided by 54.4 and y by -83.6 before it leaves the engine.
_GOAL_LINE = 55.0


def _pitch_meters(x, y, z):
  """Camera meters for a ball position read from Python."""
  return (float(x) * 54.4, float(y) * -83.6, max(0.4, float(z)))


def _ball_reset(before_x, after_x):
  """True when a goal drops the ball back on the center spot."""
  return abs(before_x) > _GOAL_LINE and abs(after_x) < 40.0


def _ball_point(env):
  try:
    ball = env._env.get_info().ball_position
    return _pitch_meters(ball[0], ball[1], ball[2])
  except (TypeError, ValueError, AttributeError, IndexError):
    return (0.0, 0.0, 1.0)


def _picture_size(pixels):
  """Width and height for an RGB buffer. The pitch is near 16:9."""
  if pixels <= 0:
    return None
  best = None
  root = int(math.sqrt(pixels))
  low = max(1, root // 4)
  high = min(pixels, root * 4)
  for height in range(low, high + 1):
    if pixels % height:
      continue
    width = pixels // height
    if width < height:
      continue
    error = abs((width / float(height)) - (16.0 / 9.0))
    if best is None or error < best[0]:
      best = (error, width, height)
  if best is None or best[0] > 0.55:
    return None
  return best[1], best[2]


def _frame_repeats(seconds):
  """How many 60fps video frames stand in for this much screen time."""
  return max(1, int(round(float(seconds) * 60.0)))


def moment_load_percent(written, goal, shown=0):
  """How full the key-moment bar is, and the goal used for the next reading.

  The bar stays under 100 until the file is ready. If the clip runs longer
  than the first guess, the goal moves with the frames already written and
  the bar stays at 99 instead of jumping backwards.
  """
  written = max(0, int(written))
  goal = max(1, int(goal))
  shown = max(0, min(99, int(shown)))
  if written > goal:
    goal = written
  percent = min(99, max(shown, int(written * 99 / goal)))
  return percent, goal


# How many seeds to try for a stretch that does not score.
_COMPARE_TRIES = 24
# Blind steps are cheaper than a drawn picture. This many weigh as one
# picture on the loading bar, so the search does not finish the bar.
_COMPARE_BLIND = 8


def _same_score(start, end):
  """True when the stretch did not produce a goal for either side."""
  try:
    return (int(start[0]), int(start[1])) == (int(end[0]), int(end[1]))
  except (TypeError, ValueError, IndexError):
    return False


def _match_score(env):
  info = env._env.get_info()
  return (int(info.left_goals), int(info.right_goals))


def compare_load_goal(reality_frames, alternate_frames, look_frames=0):
  """How many pictures a counterfactual comparison has to produce.

  Both filmed stretches count, and so does every frame of the broadcast
  that follows. The side-by-side write is most of that broadcast. A camera
  move is one broadcast frame each, not two: it is already paced to be read.
  """
  reality_frames = max(0, int(reality_frames))
  alternate_frames = max(0, int(alternate_frames))
  pairs = max(reality_frames, alternate_frames, 1)
  look_frames = max(0, min(int(look_frames), pairs))
  play = pairs - look_frames
  compose = (
      broadcast.OPEN_FRAMES + broadcast.COMPARE_HOLD
      + play * 2
      + look_frames
      + broadcast.COMPARE_TAIL
      + broadcast.CLOSE_FRAMES
  )
  return reality_frames + alternate_frames + compose


def _snapshot_play(env):
  """Ball, who has it, and the score, for comparing two runs of one stretch."""
  ball = _ball_point(env)
  try:
    info = env._env.get_info()
    owner = (int(info.ball_owned_team), int(info.ball_owned_player))
    score = (int(info.left_goals), int(info.right_goals))
  except (TypeError, ValueError, AttributeError):
    owner = (-1, -1)
    score = (0, 0)
  return {
      'ball': (float(ball[0]), float(ball[1])),
      'owner': owner,
      'score': score,
  }


def compare_beats(reality, alternate):
  """Where both pictures freeze together.

  The split is the first moment the balls are clearly apart. The chance is
  the reality frame the score changes. A split that is already the chance
  is not frozen twice.
  """
  count = min(len(reality or []), len(alternate or []))
  if count < 2:
    return []
  start = tuple(reality[0]['score'])
  chance = None
  for index in range(count):
    if tuple(reality[index]['score']) != start:
      chance = index
      break
  split = None
  for index in range(8, count):
    left = reality[index]['ball']
    right = alternate[index]['ball']
    dist = math.hypot(left[0] - right[0], left[1] - right[1])
    owners = tuple(reality[index]['owner']) != tuple(alternate[index]['owner'])
    if dist >= 4.0 or (owners and dist >= 2.0):
      split = index
      break
  beats = []
  if split is not None and (chance is None or split + 20 < chance):
    beats.append(('split', split))
  if chance is not None and chance > 0:
    beats.append(('chance', chance))
  return beats


def _compare_look_parts():
  """Hold, move in, hold, and come back. The same count on both sides."""
  return (
      _frame_repeats(0.5),
      _frame_repeats(0.8),
      _frame_repeats(1.2),
      _frame_repeats(0.7),
  )


def _compare_look_frames():
  return sum(_compare_look_parts())


def _compare_segments(physics, beats, study_len):
  """Play frames and camera-move frames in the order the side videos store them."""
  physics = max(0, int(physics))
  study_len = max(0, int(study_len))
  indexes = sorted(int(index) for index in beats if 0 <= int(index) < physics)
  segments = []
  cursor = 0
  for index in indexes:
    play = index - cursor + 1
    if play > 0:
      segments.append(('play', play))
    if study_len:
      segments.append(('look', study_len))
    cursor = index + 1
  if cursor < physics:
    segments.append(('play', physics - cursor))
  return segments


def _moment_frame_goal(start, end):
  """A first guess at how many video frames this key moment will write."""
  try:
    steps = saves.step_for_clock(int(end)) - saves.step_for_clock(int(start))
  except (TypeError, ValueError):
    steps = 300
  steps = max(30, int(steps))
  # Two fullbacks, the hold on each, and the return. Plus the ball in the net.
  fullbacks = int(round(60.0 * (0.85 + 2 * (0.85 + 1.05) + 0.9)))
  return (
      broadcast.OPEN_FRAMES + steps + 16 + 120 + fullbacks + broadcast.CLOSE_FRAMES
  )


def _read_picture(env):
  """The frame just drawn, bottom-up RGB from the engine, as BGR."""
  raw = env._env.get_frame()
  if not raw:
    return None
  count = len(raw) // 3
  if count < 16 or count * 3 != len(raw):
    return None
  size = _picture_size(count)
  if size is None:
    return None
  width, height = size
  image = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3))
  image = cv2.cvtColor(np.flipud(image), cv2.COLOR_RGB2BGR)
  return np.ascontiguousarray(image)


def _draw_picture(env, reuse=False):
  """Draw the next picture without putting it on the match window.

  The player meshes are rebuilt only while rendering is on. Turn it on for
  this draw, then off again so the next step does not present the frame.
  A camera move over a held pose reuses the meshes and the shadow already
  drawn, instead of skinning and shadowing the same bodies again.
  """
  config = env._env.game_config
  config.reuse_meshes = bool(reuse)
  config.render = True
  try:
    env._env.render(False)
  finally:
    config.render = False
    config.reuse_meshes = False
  env._env.poll_window(0.0)
  return _read_picture(env)


def _focus_distance(pose):
  """Metres from the free camera to the pitch point it is aimed at.

  The long-lens blur uses this. A look that misses the pitch stays sharp.
  """
  height = float(pose[2])
  look_z = math.sin(float(pose[4]))
  if look_z >= -0.05:
    return 0.0
  distance = (1.0 - height) / look_z
  if distance < 1.0:
    return 0.0
  return distance


def _draw_pose(env, live, pose, fov, reuse=True):
  live.set_camera({
      'team': -1,
      'player': 0,
      'lens': 3,
      'x': pose[0],
      'y': pose[1],
      'z': pose[2],
      'yaw': pose[3],
      'pitch': pose[4],
  })
  use_camera(env, live)
  env._env.game_config.camera_fov = fov
  env._env.game_config.camera_focus = _focus_distance(pose)
  return _draw_picture(env, reuse=reuse)


class _ClipEncoder(object):
  """A 60fps mp4 of the key moment. Frames are written and dropped."""

  def __init__(self, path):
    self.path = path
    self.writer = None
    self.size = None
    self.last = None
    self.written = 0
    self.progress = None

  def write(self, image, repeats, plate=None):
    if image is None:
      return False
    height, width = image.shape[:2]
    width -= width % 2
    height -= height % 2
    if width < 16 or height < 16:
      return False
    if image.shape[1] != width or image.shape[0] != height:
      image = np.ascontiguousarray(image[:height, :width])
    if self.writer is None:
      folder = os.path.dirname(self.path)
      if folder:
        os.makedirs(folder, exist_ok=True)
      fourcc = cv2.VideoWriter_fourcc(*'avc1')
      writer = cv2.VideoWriter(self.path, fourcc, 60.0, (width, height))
      if not writer.isOpened():
        writer.release()
        return False
      self.writer = writer
      self.size = (width, height)
    target_w, target_h = self.size
    if image.shape[1] != target_w or image.shape[0] != target_h:
      image = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_AREA)
    self.last = image
    count = max(1, int(repeats))
    # Stamp every output frame. The ribbon pattern keeps moving after the
    # score bar has finished extending, including on a repeated picture.
    for _ in range(count):
      frame = image if plate is None else plate.stamp(image)
      if frame.shape[1] != target_w or frame.shape[0] != target_h:
        frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
      self.writer.write(frame)
    self.written += count
    if self.progress:
      self.progress(self.written)
    return True

  def close(self):
    if self.writer is not None:
      self.writer.release()
      self.writer = None


def _clip_file(token):
  folder = os.path.join(tempfile.gettempdir(), 'branchplay-clips')
  return os.path.join(folder, '%x.mp4' % int(token))


def _preview_file(token):
  folder = os.path.join(tempfile.gettempdir(), 'branchplay-clips')
  os.makedirs(folder, exist_ok=True)
  return os.path.join(folder, '%x.webp' % int(token))


def _clip_media_type(path):
  if str(path).lower().endswith('.webp'):
    return 'image/webp'
  return 'video/mp4'


def _faststart(path):
  """Move the mp4 header to the front so the player can start immediately."""
  ffmpeg = shutil.which('ffmpeg')
  if not ffmpeg or not os.path.isfile(path):
    return
  temporary = path + '.fast.mp4'
  try:
    result = subprocess.run(
        [ffmpeg, '-y', '-loglevel', 'error', '-i', path, '-c', 'copy',
         '-movflags', '+faststart', temporary],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0 and os.path.getsize(temporary) > 64:
      os.replace(temporary, path)
  except OSError:
    pass
  finally:
    if os.path.isfile(temporary):
      _delete_clip(temporary)


def _arm_plate(plate, env, clock, reveal_at):
  """Point the broadcast frame at this picture's clock and score."""
  if plate is None:
    return
  try:
    info = env._env.get_info()
    score = (int(info.left_goals), int(info.right_goals))
  except (TypeError, ValueError, AttributeError):
    score = plate.score
  plate.set_state(clock, score, int(clock) >= int(reveal_at))


def _ease_pose(env, live, token, clip, origin, reveal, seconds, fov, plate=None,
               clock=0, reveal_at=0, end_fov=None):
  frames = max(8, int(round(seconds * 60.0)))
  if end_fov is None:
    end_fov = fov
  for index in range(frames):
    if not live.moment_active(token) or live.quit_requested():
      return False
    t = index / float(frames - 1)
    t = t * t * (3.0 - 2.0 * t)
    frame_fov = fov + (end_fov - fov) * t
    image = _draw_pose(env, live, _mix_pose(origin, reveal, t), frame_fov)
    _arm_plate(plate, env, clock, reveal_at)
    if not clip.write(image, 1, plate):
      return False
  return True


def _settle_net(env, live, token, clip, plate, clock, reveal_at, pose, velocity):
  """Hold the last picture of the goal and let the camera finish its move.

  The ball has already played through every frame before the restart. This
  keeps that last touch on screen. The camera keeps the direction it had,
  slowing down, so the cut is the same shot rather than a frozen frame.
  A camera that had already stopped is left where it is.
  """
  if pose is None or velocity is None:
    return True
  speed = math.hypot(velocity[0], velocity[1], velocity[2])
  if speed < 0.02 and abs(velocity[3]) < 0.005 and abs(velocity[4]) < 0.005:
    return True
  frames = _frame_repeats(2.0)
  tau = 0.85
  current = pose
  vel = list(velocity)
  first = True
  for _ in range(frames):
    if not live.moment_active(token) or live.quit_requested():
      return False
    dt = 1.0 / 60.0
    decay = math.exp(-dt / tau)
    for index in range(5):
      vel[index] *= decay
    current = _step_pose(current, vel, dt)
    # The restored pose has to be skinned once. Later frames only move
    # the camera.
    image = _draw_pose(env, live, current, 12.0, reuse=not first)
    first = False
    _arm_plate(plate, env, clock, reveal_at)
    if not clip.write(image, 1, plate):
      return False
  return True


def _hold_pose(env, live, token, clip, pose, fov, seconds, plate=None, clock=0,
               reveal_at=0):
  if not live.moment_active(token) or live.quit_requested():
    return False
  image = _draw_pose(env, live, pose, fov)
  _arm_plate(plate, env, clock, reveal_at)
  return clip.write(image, _frame_repeats(seconds), plate)


def _defending_side(rows, start, end):
  """The team whose fullbacks the goal got past. An own goal is that team."""
  start = int(start)
  end = int(end)
  side = None
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    clock = saves.clock_seconds(row.get('clock'))
    if clock < start or clock > end:
      continue
    action = str(row.get('action') or '').upper()
    try:
      team = int(row.get('team'))
    except (TypeError, ValueError):
      continue
    if action == 'OWN GOAL':
      side = team
    elif action == 'GOAL':
      side = 1 - team
  return side


def _fullback_indexes(roles):
  """Roster indexes whose role is left back or right back."""
  found = []
  for index, role in enumerate(roles or []):
    try:
      number = int(role)
    except (TypeError, ValueError):
      continue
    if number in (2, 3):
      found.append(index)
  return found


def _picture_xy(env, team, position):
  """On-screen metres for one player, the same place the mesh is drawn.

  Team 1 is already mirrored in the observation, matching the mesh. The
  ball uses that same on-screen space. Mirroring again aims the camera
  at the empty half of the pitch.
  """
  del env, team
  return float(position[0]) * 54.4, float(position[1]) * -83.6


def _fullback_marks(env, rows, start, end):
  """The defending fullbacks, with a name and a place in the picture."""
  side = _defending_side(rows, start, end)
  if side is None:
    return []
  try:
    info = env._env.get_info()
    players = info.left_team if side == 0 else info.right_team
  except (TypeError, ValueError, AttributeError):
    return []
  named = {}
  try:
    for row in env._env.hud_feed().get('players') or []:
      named[(int(row['team']), int(row['player']))] = row
  except (TypeError, ValueError, AttributeError, KeyError):
    named = {}
  marks = []
  for index in _fullback_indexes(player.role for player in players):
    player = players[index]
    try:
      if not bool(player.is_active):
        continue
    except (TypeError, ValueError, AttributeError):
      pass
    row = named.get((side, index), {})
    text = str(row.get('surname') or row.get('name') or '').strip().upper()
    if not text:
      try:
        text = 'LB' if int(player.role) == 2 else 'RB'
      except (TypeError, ValueError, AttributeError):
        text = 'FULLBACK'
    try:
      x, y = _picture_xy(env, side, player.position)
    except (TypeError, ValueError, AttributeError, IndexError):
      continue
    marks.append({
        'team': side,
        'player': index,
        'text': text,
        'x': x,
        'y': y,
    })
  return marks


def _set_moment_marks(env, marks):
  payload = []
  for mark in marks or []:
    payload.append({
        'team': int(mark['team']),
        'player': int(mark['player']),
        'text': str(mark['text']) if 'text' in mark else 'FULLBACK',
        'shape': int(mark.get('shape') or 0),
    })
  try:
    env._env.set_moment_marks(payload)
  except AttributeError:
    pass


def _order_fullbacks(marks, ball):
  """Nearest the ball first, then left to right when two are the same distance."""
  bx, by = float(ball[0]), float(ball[1])

  def key(mark):
    return (
        (mark['x'] - bx) ** 2 + (mark['y'] - by) ** 2,
        mark['x'],
        mark.get('player', 0),
    )

  return sorted(marks, key=key)


def _fullback_close_pose(origin, point):
  """A long-lens frame a short way off one fullback, from the camera's side."""
  px, py = float(point[0]), float(point[1])
  dx = float(origin[0]) - px
  dy = float(origin[1]) - py
  dist = math.hypot(dx, dy) or 1.0
  reach = 14.0
  return _aim_pose(
      px + dx / dist * reach,
      py + dy / dist * reach,
      3.4,
      px, py, 1.1,
  ), 12.0


def _roster_index(env, team, shirt):
  """Roster slot for a shirt, the same index the engine marks use."""
  try:
    feed = env._env.hud_feed().get('players') or []
  except (TypeError, ValueError, AttributeError):
    return None
  for row in feed:
    try:
      if int(row['team']) != int(team):
        continue
      if int(row.get('shirt') or -1) != int(shirt):
        continue
      return int(row['player'])
    except (TypeError, ValueError, KeyError):
      continue
  return None


def _player_xy(env, team, shirt):
  """Where one roster player stands, in picture metres."""
  index = _roster_index(env, team, shirt)
  try:
    info = env._env.get_info()
    players = info.left_team if int(team) == 0 else info.right_team
  except (TypeError, ValueError, AttributeError):
    return None
  if index is None or index < 0 or index >= len(players):
    return None
  try:
    return _picture_xy(env, int(team), players[index].position)
  except (TypeError, ValueError, AttributeError, IndexError):
    return None


def _scorer_distance(env, identity):
  """Metres from the ball to the scorer, in the on-screen plane.

  Both are in the picture's coordinates. A ball still well above the
  player does not count as arrived.
  """
  if not identity:
    return None
  place = _player_xy(env, identity[0], identity[1])
  if place is None:
    return None
  ball = _ball_point(env)
  gap = math.hypot(ball[0] - place[0], ball[1] - place[1])
  if ball[2] > 1.0:
    gap = math.hypot(gap, ball[2] - 0.4)
  return gap


_SCORER_MARK_FRAMES = 5 * 60


def _scorer_mark(env, rows, start, end):
  """A downward triangle on the player who will score."""
  identity = _scorer_identity(rows, start, end)
  if not identity:
    return None
  index = _roster_index(env, identity[0], identity[1])
  if index is None or index < 0:
    return None
  return {
      'team': int(identity[0]),
      'player': index,
      'text': '',
      'shape': 1,
  }


def _show_fullbacks(env, live, token, clip, plate, clock, reveal_at, rows,
                    start, end):
  """Hold, then visit each defending fullback, then return to the touch.

  The ring and the name follow the player the camera is on. The marks come
  off when the camera returns to the scoring touch.
  """
  marks = _fullback_marks(env, rows, start, end)
  if not marks:
    return True
  _draw_picture(env)
  origin = _read_pose(env)
  if origin is None:
    return True
  ordered = _order_fullbacks(marks, _ball_point(env))
  try:
    # Sit on the freeze before the first pan.
    if not _hold_pose(
        env, live, token, clip, origin, 12.0, 0.85, plate, clock, reveal_at):
      return False
    pose = origin
    fov = 12.0
    for mark in ordered:
      _set_moment_marks(env, [mark])
      close, close_fov = _fullback_close_pose(pose, (mark['x'], mark['y']))
      if not _ease_pose(
          env, live, token, clip, pose, close, 0.85, fov, plate, clock,
          reveal_at, close_fov):
        return False
      if not _hold_pose(
          env, live, token, clip, close, close_fov, 1.05, plate, clock,
          reveal_at):
        return False
      pose, fov = close, close_fov
    _set_moment_marks(env, [])
    return _ease_pose(
        env, live, token, clip, pose, origin, 0.9, fov, plate, clock,
        reveal_at, 12.0)
  finally:
    _set_moment_marks(env, [])


def _publish_moment(env, live, phase, clip=None, status=None, progress=None,
                    kind=None):
  """Publish a key-moment phase without moving the clock the panel is showing.

  A passed status is the picture from before the clip was simulated. The
  engine is somewhere else while the video is being made.
  """
  if status is None:
    status = window_status(env, True)
    status['phase'] = 'view' if live.viewing() else 'menu'
    _attach_possession(status, live)
    _attach_timeline(status, live)
  else:
    status = dict(status)
  if phase:
    status['moment'] = phase
  else:
    status.pop('moment', None)
  if progress is not None:
    status['progress'] = round(max(0.0, min(0.99, float(progress))), 4)
  if kind:
    status['clip_kind'] = kind
  else:
    status.pop('clip_kind', None)
  clip_id = live.moment_id()
  if clip_id is not None:
    status['clip_id'] = clip_id
  if clip:
    status['clip'] = clip
  else:
    status.pop('clip', None)
  live.publish(None, status)


class _FrameWriter(object):
  """A temporary picture sequence. One frame per physics step."""

  def __init__(self, path):
    self.path = path
    self.writer = None
    self.size = None
    self.count = 0

  def write(self, image):
    if image is None:
      return False
    height, width = image.shape[:2]
    width -= width % 2
    height -= height % 2
    if width < 16 or height < 16:
      return False
    image = np.ascontiguousarray(image[:height, :width])
    if self.writer is None:
      folder = os.path.dirname(self.path)
      if folder:
        os.makedirs(folder, exist_ok=True)
      fourcc = cv2.VideoWriter_fourcc(*'avc1')
      writer = cv2.VideoWriter(self.path, fourcc, 30.0, (width, height))
      if not writer.isOpened():
        writer.release()
        return False
      self.writer = writer
      self.size = (width, height)
    if image.shape[1] != self.size[0] or image.shape[0] != self.size[1]:
      image = cv2.resize(image, self.size, interpolation=cv2.INTER_AREA)
    self.writer.write(image)
    self.count += 1
    return True

  def close(self):
    if self.writer is not None:
      self.writer.release()
      self.writer = None


def _picture_meta(env):
  """Clock and score of the picture just drawn."""
  try:
    step = int(env._env.get_info().step)
    info = env._env.get_info()
    score = (int(info.left_goals), int(info.right_goals))
  except (TypeError, ValueError, AttributeError):
    return 0, (0, 0)
  return saves.clock_from_step(step), score


def _player_label(env, team, index):
  """Surname drawn on a comparison mark, or the shirt if there is no name."""
  try:
    rows = env._env.hud_feed().get('players') or []
  except (TypeError, ValueError, AttributeError):
    return ''
  for row in rows:
    try:
      if int(row['team']) != int(team) or int(row['player']) != int(index):
        continue
    except (TypeError, ValueError, KeyError):
      continue
    text = str(row.get('surname') or row.get('name') or '').strip().upper()
    if text:
      return text
    shirt = row.get('shirt')
    if shirt not in (None, ''):
      return str(shirt)
  return ''


def _nearest_roster(env):
  """The active player closest to the ball, as team and roster index."""
  ball = _ball_point(env)
  best = None
  try:
    info = env._env.get_info()
    sides = ((0, info.left_team), (1, info.right_team))
  except (TypeError, ValueError, AttributeError):
    return None
  for team, players in sides:
    for index, player in enumerate(players):
      try:
        if not bool(player.is_active):
          continue
      except (TypeError, ValueError, AttributeError):
        pass
      try:
        x, y = _picture_xy(env, team, player.position)
      except (TypeError, ValueError, AttributeError, IndexError):
        continue
      dist = (x - ball[0]) ** 2 + (y - ball[1]) ** 2
      if best is None or dist < best[0]:
        best = (dist, team, index)
  if best is None:
    return None
  return best[1], best[2]


def _compare_mark(env, shape, identity=None):
  """Who the frozen picture points at. A triangle names no one; a ring does."""
  team = None
  player = None
  if identity:
    index = _roster_index(env, identity[0], identity[1])
    if index is not None and index >= 0:
      team, player = int(identity[0]), int(index)
  if team is None:
    try:
      info = env._env.get_info()
      owned_team = int(info.ball_owned_team)
      owned_player = int(info.ball_owned_player)
    except (TypeError, ValueError, AttributeError):
      owned_team, owned_player = -1, -1
    if owned_team >= 0 and owned_player >= 0:
      team, player = owned_team, owned_player
    else:
      nearest = _nearest_roster(env)
      if nearest is None:
        return None
      team, player = nearest
  text = '' if int(shape) == 1 else _player_label(env, team, player)
  return {
      'team': int(team),
      'player': int(player),
      'text': text,
      'shape': int(shape),
  }


def _difference_pose(origin, ball):
  """A long lens a short way off the ball, from the side the camera is on."""
  bx, by, bz = float(ball[0]), float(ball[1]), float(ball[2])
  dx = float(origin[0]) - bx
  dy = float(origin[1]) - by
  dist = math.hypot(dx, dy) or 1.0
  reach = 11.0
  pose = _aim_pose(
      bx + dx / dist * reach,
      by + dy / dist * reach,
      2.8,
      bx, by, max(0.4, min(bz, 2.0)),
  )
  return pose, 14.0


def _write_same(film, image, count, note):
  """Write one picture several times. The count stays fixed if a later draw fails."""
  if image is None or count <= 0:
    return False
  for _ in range(int(count)):
    if not film.write(image):
      return False
    if note:
      note(film.count)
  return True


def _write_compare_look(env, live, token, film, mark, note):
  """Freeze, mark the player, move in on the ball, hold, and come back.

  The simulation does not step. Both sides use the same frame count.
  """
  hold, ease, stay, back = _compare_look_parts()
  total = hold + ease + stay + back
  try:
    if mark:
      _set_moment_marks(env, [mark])
    image = _draw_picture(env, reuse=False)
    origin = _read_pose(env)
    ball = _ball_point(env)
    if image is None or origin is None:
      return _write_same(film, image, total, note)
    if not _write_same(film, image, hold, note):
      return False
    close, close_fov = _difference_pose(origin, ball)
    frames = max(2, ease)
    last = image
    for index in range(frames):
      if not live.moment_active(token) or live.quit_requested() or _note_escape(env, live):
        return False
      t = index / float(frames - 1)
      t = t * t * (3.0 - 2.0 * t)
      drawn = _draw_pose(
          env, live, _mix_pose(origin, close, t), 18.0 + (close_fov - 18.0) * t,
          reuse=index > 0)
      if drawn is not None:
        last = drawn
      if not film.write(last):
        return False
      if note:
        note(film.count)
    if not _write_same(film, last, stay, note):
      return False
    frames = max(2, back)
    for index in range(frames):
      if not live.moment_active(token) or live.quit_requested() or _note_escape(env, live):
        return False
      t = index / float(frames - 1)
      t = t * t * (3.0 - 2.0 * t)
      drawn = _draw_pose(
          env, live, _mix_pose(close, origin, t), close_fov + (18.0 - close_fov) * t,
          reuse=True)
      if drawn is not None:
        last = drawn
      if not film.write(last):
        return False
      if note:
        note(film.count)
    return True
  finally:
    _set_moment_marks(env, [])
    _set_action_camera(env, live)
    env._env.game_config.camera_fov = 0.0
    env._env.game_config.camera_focus = 0.0


def _film_stretch(env, live, token, end_clock, path, note, beat_kinds=None, mark_for=None):
  """Record the action camera from the pose on screen through end_clock.

  The first frame is the pose already there. Each later frame is one step.
  At a beat, the picture freezes and the camera moves in before play continues.
  Returns the per-step clock and score, and how many pictures were written.
  """
  film = _FrameWriter(path)
  beat_kinds = beat_kinds or {}
  metas = []
  try:
    def look_now():
      kind = beat_kinds.get(len(metas) - 1)
      if not kind:
        return True
      mark = mark_for(kind) if mark_for else None
      return _write_compare_look(env, live, token, film, mark, note)

    image = _draw_picture(env)
    if image is None or not film.write(image):
      return None
    metas.append(_picture_meta(env))
    note(film.count)
    if not look_now():
      return None
    guard = 0
    try:
      room = saves.step_for_clock(int(end_clock)) - int(env._env.get_info().step)
    except (TypeError, ValueError, AttributeError):
      room = 400
    room = max(8, int(room) + 4)
    while (
        live.moment_active(token)
        and not live.quit_requested()
        and not live.home_pending()):
      if _note_escape(env, live):
        return None
      step = int(env._env.get_info().step)
      clock = saves.clock_from_step(step)
      if clock >= int(end_clock) or step >= int(env._env.config.game_duration) - 1:
        break
      if guard >= room:
        break
      env._env.game_config.render = False
      env._env.step()
      image = _draw_picture(env)
      if image is None or not film.write(image):
        break
      metas.append(_picture_meta(env))
      guard += 1
      note(film.count)
      if not look_now():
        return None
    if not metas:
      return None
    return metas, film.count
  finally:
    film.close()


def _roll_stretch(env, live, token, end_clock, note):
  """Step without drawing until end_clock.

  Returns how many steps were taken, or None if the viewer leaves.
  """
  guard = 0
  try:
    room = saves.step_for_clock(int(end_clock)) - int(env._env.get_info().step)
  except (TypeError, ValueError, AttributeError):
    room = 400
  room = max(8, int(room) + 4)
  while (
      live.moment_active(token)
      and not live.quit_requested()
      and not live.home_pending()):
    if _note_escape(env, live):
      return None
    try:
      step = int(env._env.get_info().step)
    except (TypeError, ValueError, AttributeError):
      return None
    if (
        saves.clock_from_step(step) >= int(end_clock)
        or step >= int(env._env.config.game_duration) - 1):
      return guard
    if guard >= room:
      return guard
    env._env.game_config.render = False
    env._env.step()
    guard += 1
    if note:
      note(guard)
    if guard % 8 == 0:
      env._env.poll_window(0.0)
  return None


def _seek_scoreless(
    env, live, token, origin, end_clock, base_seed, start_clock, start_score, note):
  """A seed whose run of this stretch does not score.

  Each try is the same length as the key moment and is not drawn. None if
  every try scores, or the viewer leaves.
  """
  done = 0
  for attempt in range(_COMPARE_TRIES):
    if (
        not live.moment_active(token) or live.quit_requested()
        or live.home_pending()):
      return None
    _restore_state(env, live, origin)
    seed = _branch_seed(base_seed, attempt + 1, start_clock)
    env._env.reseed(int(seed))
    env._env.clear_touches()
    env._env.game_config.render = False

    attempt_trace = [_snapshot_play(env)]

    def on_step(guard, base=done, bucket=attempt_trace):
      bucket.append(_snapshot_play(env))
      if note:
        note(base + guard)

    taken = _roll_stretch(env, live, token, end_clock, on_step)
    if taken is None:
      return None
    done += int(taken)
    try:
      if _same_score(start_score, _match_score(env)):
        return seed, done, attempt_trace
    except (TypeError, ValueError, AttributeError):
      continue
  return None


def _read_pair(left_cap, right_cap, last):
  """The next picture from each side. A side that has ended holds."""
  ok_left, left = left_cap.read()
  ok_right, right = right_cap.read()
  if not ok_left and not ok_right:
    return None
  if ok_left:
    left = left.copy()
  else:
    left = None if last[0] is None else last[0].copy()
  if ok_right:
    right = right.copy()
  else:
    right = None if last[1] is None else last[1].copy()
  if left is None or right is None:
    return None
  last[0] = left
  last[1] = right
  return left, right


def _play_compare(env, live, start, end, token, panel):
  """Film the moment and one reseeded run, then play them side by side.

  Both start from the same pose. The new run lasts until the same clock.
  Seeds are tried, without drawing, until one of them does not score.
  That run is saved off the timeline. The picture is a broadcast, not the
  match panels.
  """
  if (
      not live.moment_active(token) or not live.can_branch()
      or not hasattr(env._env, 'reseed')):
    return
  folder = os.path.dirname(_clip_file(token))
  reality_path = os.path.join(folder, 'reality-%x.mp4' % int(token))
  alternate_path = os.path.join(folder, 'alternate-%x.mp4' % int(token))
  out_path = os.path.join(folder, 'compare-%x.mp4' % int(token))
  sent = [-1]
  goal = [1]

  def report(done):
    percent, goal[0] = moment_load_percent(int(done), goal[0], max(0, sent[0]))
    if percent == sent[0]:
      return
    sent[0] = percent
    _publish_moment(
        env, live, 'loading', status=panel, progress=percent / 100.0)

  try:
    _publish_moment(env, live, 'loading', status=panel, progress=0.0)
    _scrub_to(env, live, start, force=True, present=False)
    if not live.moment_active(token) or not live.viewing():
      return
    _set_action_camera(env, live)
    env._env.game_config.camera_fov = 0.0
    env._env.game_config.camera_focus = 0.0
    env._env.game_config.render = False
    env._env.set_held(False)
    env._env.set_action_labels(False)
    _set_moment_marks(env, [])
    try:
      origin = _state_blob(env.get_state({}))
      start_step = int(env._env.get_info().step)
    except (TypeError, ValueError, AttributeError):
      return
    start_clock = saves.clock_from_step(start_step)
    try:
      start_score = _match_score(env)
    except (TypeError, ValueError, AttributeError):
      return
    expect = max(1, saves.step_for_clock(int(end)) - start_step)
    try:
      base_seed = int(env._env.config.game_engine_random_seed)
    except (TypeError, ValueError, AttributeError):
      base_seed = 1
    blind_cap = (_COMPARE_TRIES * expect) // _COMPARE_BLIND
    goal[0] = blind_cap + compare_load_goal(expect, expect)
    found = _seek_scoreless(
        env, live, token, origin, end, base_seed, start_clock, start_score,
        lambda steps: report(int(steps) // _COMPARE_BLIND))
    if not found:
      if live.moment_active(token) and not live.home_pending():
        print('No counterfactual without a goal.', flush=True)
      return
    seed, blind_steps, alternate_trace = found
    used = int(blind_steps) // _COMPARE_BLIND
    _restore_state(env, live, origin)
    reality_trace = [_snapshot_play(env)]

    def record_reality(guard, base=used):
      reality_trace.append(_snapshot_play(env))
      report(base + int(guard) // _COMPARE_BLIND)

    if _roll_stretch(env, live, token, end, record_reality) is None:
      return
    used = used + int(len(reality_trace) - 1) // _COMPARE_BLIND
    beats = compare_beats(reality_trace, alternate_trace)
    study = len(beats) * _compare_look_frames()
    beat_kinds = {index: kind for kind, index in beats}
    scorer = _scorer_identity(live.touch_list(), start, end)
    goal[0] = used + compare_load_goal(expect + study, expect + study, study)
    report(used)

    def reality_mark(kind):
      if kind == 'chance':
        return _compare_mark(env, 1, scorer)
      return _compare_mark(env, 0, None)

    def alternate_mark(kind):
      del kind
      return _compare_mark(env, 0, None)

    _restore_state(env, live, origin)
    _set_action_camera(env, live)
    env._env.game_config.camera_fov = 0.0
    env._env.game_config.camera_focus = 0.0
    env._env.game_config.render = False
    env._env.set_held(False)
    env._env.set_action_labels(False)
    _set_moment_marks(env, [])
    reality = _film_stretch(
        env, live, token, end, reality_path,
        lambda count: report(used + count), beat_kinds, reality_mark)
    if not reality or not live.moment_active(token) or live.home_pending():
      return
    reality_metas, reality_written = reality
    _restore_state(env, live, origin)
    env._env.reseed(int(seed))
    env._env.clear_touches()
    _set_action_camera(env, live)
    env._env.game_config.camera_fov = 0.0
    env._env.game_config.render = False
    env._env.set_held(False)
    env._env.set_action_labels(False)
    alternate = _film_stretch(
        env, live, token, end, alternate_path,
        lambda count: report(used + reality_written + count),
        beat_kinds, alternate_mark)
    if not alternate or not live.moment_active(token) or live.home_pending():
      return
    alternate_metas, alternate_written = alternate
    branch_id = str(int(live.next_branch_id()))
    try:
      info = env._env.get_info()
      end_step = int(info.step)
      record = {
          'id': branch_id,
          'parent': live.line_id() or None,
          'clock': start_clock,
          'step': start_step,
          'end_clock': saves.clock_from_step(end_step),
          'end_step': end_step,
          'minutes': None,
          'score': [int(info.left_goals), int(info.right_goals)],
          'seed': int(seed),
          'marks': [{
              'step': start_step,
              'clock': start_clock,
              'state': origin,
          }],
          'touches': _touch_rows(env),
          'on_timeline': False,
      }
      record['added'] = _added_players(env)
      saves.write_branch(live.sim_id(), record)
      live.add_branch(record)
    except (OSError, struct.error, ValueError, AttributeError) as error:
      print('Branch was not saved: %s' % error, flush=True)
    goal[0] = used + compare_load_goal(
        reality_written, alternate_written, study)
    report(used + reality_written + alternate_written)
    minute = broadcast.goal_minute(int(end))
    plate = broadcast.ComparePlate(
        panel.get('left_name'), panel.get('right_name'), minute,
        live.clip_language())
    left_cap = cv2.VideoCapture(reality_path)
    right_cap = cv2.VideoCapture(alternate_path)
    clip = _ClipEncoder(out_path)
    try:
      first = _read_pair(left_cap, right_cap, [None, None])
      if first is None:
        return
      left0, right0 = first
      clock0, score0 = reality_metas[0]
      _, other0 = alternate_metas[0]
      plate.set_state(clock0, score0, other0)
      cursor = [used + reality_written + alternate_written]

      def tick():
        cursor[0] += 1
        report(cursor[0])

      for _ in range(broadcast.OPEN_FRAMES + broadcast.COMPARE_HOLD):
        if (
            not live.moment_active(token) or live.quit_requested()
            or live.home_pending() or _note_escape(env, live)):
          return
        if not clip.write(plate.stamp(left0, right0), 1, None):
          return
        tick()
      last = [left0, right0]
      pending = [first]

      def take_pair():
        if pending[0] is not None:
          pair = pending[0]
          pending[0] = None
          return pair
        return _read_pair(left_cap, right_cap, last)

      segments = _compare_segments(
          min(len(reality_metas), len(alternate_metas)),
          [index for _kind, index in beats],
          _compare_look_frames() if beats else 0)
      physics = 0
      for kind, count in segments:
        repeats = 2 if kind == 'play' else 1
        for _ in range(count):
          if (
              not live.moment_active(token) or live.quit_requested()
              or live.home_pending() or _note_escape(env, live)):
            return
          pair = take_pair()
          if pair is None:
            pair = (last[0], last[1])
          else:
            last[0], last[1] = pair
          if kind == 'play':
            meta_i = min(physics, len(reality_metas) - 1)
            other_i = min(physics, len(alternate_metas) - 1)
            physics += 1
          else:
            meta_i = min(max(0, physics - 1), len(reality_metas) - 1)
            other_i = min(max(0, physics - 1), len(alternate_metas) - 1)
          plate.set_state(
              reality_metas[meta_i][0], reality_metas[meta_i][1],
              alternate_metas[other_i][1])
          for _repeat in range(repeats):
            if not clip.write(plate.stamp(pair[0], pair[1]), 1, None):
              return
            tick()
      if clip.last is None or not live.moment_active(token) or live.home_pending():
        return
      tail_left, tail_right = last
      for _ in range(broadcast.COMPARE_TAIL):
        if not live.moment_active(token) or live.quit_requested() or _note_escape(env, live):
          return
        if not clip.write(plate.stamp(tail_left, tail_right), 1, None):
          return
        tick()
      plate.begin_close()
      for _ in range(broadcast.CLOSE_FRAMES):
        if not live.moment_active(token) or live.quit_requested() or _note_escape(env, live):
          return
        if not clip.write(plate.stamp(tail_left, tail_right), 1, None):
          return
        tick()
    finally:
      left_cap.release()
      right_cap.release()
      clip.close()
    if not live.moment_active(token) or live.home_pending():
      return
    _faststart(out_path)
    if not os.path.isfile(out_path) or os.path.getsize(out_path) <= 64:
      return
    live.remember_clip(out_path)
    _publish_moment(
        env, live, 'ready', '/clips/' + os.path.basename(out_path), panel,
        kind='compare')
    while (
        live.moment_active(token)
        and not live.clip_finished()
        and not live.quit_requested()
        and not _note_escape(env, live)):
      env._env.poll_window(0.0)
      time.sleep(0.05)
  finally:
    _delete_clip(reality_path)
    _delete_clip(alternate_path)
    live.clear_clip(out_path)
    _delete_clip(out_path)


def _publish_panel(live, panel):
  """Publish the picture from before a preview, with the article attached."""
  if live.home_pending() or live.quit_requested():
    return
  status = dict(panel)
  _attach_timeline(status, live)
  live.publish(None, status)


def _open_brief(env, live, start, end, token):
  """Show the article for one stretch and a small looping picture of it.

  The full clip stays a separate request. The picture is drawn off the
  match window, then the camera and the clock go back.
  """
  if not live.brief_active(token):
    return
  start = max(0, int(start))
  end = max(start, int(end))
  was_held = live.frozen()
  try:
    back = saves.clock_from_step(int(env._env.get_info().step))
  except (TypeError, ValueError, AttributeError):
    back = start
  panel = window_status(env, was_held)
  panel['phase'] = 'view' if live.viewing() else 'menu'
  _attach_possession(panel, live)
  _attach_timeline(panel, live)
  left = match_chat.display_name(panel.get('left_name'), 'Left')
  right = match_chat.display_name(panel.get('right_name'), 'Right')
  rows = moment_page.segment_rows(live.touch_list(), start, end)
  language = live.clip_language()
  live.set_brief(
      title=moment_page.heading(rows, left, right, language),
      span=moment_page.span_label(start, end),
      phase='writing',
      lead='',
      preview='',
      progress=0,
  )
  _publish_panel(live, panel)

  def write_lead():
    try:
      lead = moment_page.explain(rows, left, right, language)
    except moment_page.MomentPageError as error:
      cause = error.__cause__
      if cause is not None:
        print('moment page: %s' % cause, flush=True)
      lead = str(error)
    if live.brief_active(token):
      live.set_brief(lead=lead, phase='ready')

  threading.Thread(target=write_lead, name='moment-page', daemon=True).start()
  if not live.viewing() or not live.brief_active(token):
    return
  saved = live.camera()
  entered = False
  frames = []
  preview_path = _preview_file(token)
  try:
    _scrub_to(env, live, start, force=True, present=False)
    entered = True
    if not live.viewing() or not live.brief_active(token):
      return
    try:
      landed = saves.clock_from_step(int(env._env.get_info().step))
    except (TypeError, ValueError, AttributeError):
      landed = start
    if landed > end:
      return
    _set_action_camera(env, live)
    env._env.game_config.render = False
    env._env.set_held(False)
    env._env.set_action_labels(False)
    span_steps = max(
        1, saves.step_for_clock(end) - saves.step_for_clock(start))
    stride = max(1, span_steps // moment_page.PREVIEW_FRAMES)
    duration = int(env._env.config.game_duration)

    def grab():
      image = _draw_picture(env)
      if image is None:
        return
      small = cv2.resize(
          image, moment_page.PREVIEW_SIZE, interpolation=cv2.INTER_AREA)
      frames.append(small)

    grab()
    index = 0
    while (
        live.brief_active(token)
        and not live.quit_requested()
        and not live.home_pending()):
      if _note_escape(env, live):
        break
      step = int(env._env.get_info().step)
      clock = saves.clock_from_step(step)
      if clock >= end or step >= duration - 1:
        break
      env._env.game_config.render = False
      env._env.step()
      index += 1
      clock = saves.clock_from_step(int(env._env.get_info().step))
      if index % stride == 0 or clock >= end:
        grab()
      elif index % 20 == 0:
        env._env.poll_window(0.0)
      if index % 10 == 0:
        live.set_brief(progress=min(0.95, index / float(span_steps)))
        _publish_panel(live, panel)
      if index > span_steps + 30:
        break
    if frames and live.brief_active(token):
      chosen = moment_page.sample_frames(frames, moment_page.PREVIEW_FRAMES)
      moment_page.write_preview(preview_path, chosen)
      live.remember_preview(preview_path)
      live.set_brief(
          preview='/clips/' + os.path.basename(preview_path), progress=1)
      _publish_panel(live, panel)
  except Exception as error:
    print('moment page: %s' % error, flush=True)
  finally:
    env._env.game_config.render = True
    env._env.game_config.reuse_meshes = False
    env._env.game_config.camera_fov = 0.0
    try:
      if entered and not live.home_pending() and not live.quit_requested():
        _restore_saved_camera(env, live, saved)
        if live.viewing():
          _scrub_to(env, live, back, force=True)
          if not was_held:
            env._env.set_held(False)
            live.set_frozen(False)
    finally:
      if not live.brief_active(token):
        live.drop_preview()


def _play_moment(env, live, start, end, token):
  """Record a key moment and hand the panel a video to play.

  The match window stays where the user left it. Frames are drawn and read
  without presenting them. Head labels stay off for the clip. It opens on a
  full-screen title, then that title opens onto the broadcast frame and the
  action camera runs the stretch. At the end that frame closes back onto
  the same title. When the ball reaches the scorer the
  picture holds, visits each opposing fullback, and returns for the scoring
  touch. A ring and a name mark the fullback in frame. For the opening of
  the match picture, a green triangle bobs above the player who will score.
  Slow motion is the
  scoring touch. After the goal
  the ball plays on, including the bounce in the net, until the frame
  before the restart. That last touch then holds while the camera finishes
  the move it was already making. Every physics frame is in the video. The
  file is removed when the player closes.
  """
  if not live.viewing() or not live.moment_active(token):
    if not live.moment_replaced(token):
      _publish_moment(env, live, 'done')
    return
  start = max(0, int(start))
  end = max(start, int(end))
  saved = live.camera()
  was_held = live.frozen()
  try:
    back = saves.clock_from_step(int(env._env.get_info().step))
  except (TypeError, ValueError, AttributeError):
    back = start
  panel = window_status(env, was_held)
  panel['phase'] = 'view' if live.viewing() else 'menu'
  _attach_possession(panel, live)
  _attach_timeline(panel, live)
  path = _clip_file(token)
  clip = _ClipEncoder(path)
  try:
    _publish_moment(env, live, 'loading', status=panel)
    if not live.moment_active(token):
      return
    _scrub_to(env, live, start, force=True, present=False)
    if not live.viewing() or not live.moment_active(token):
      return
    try:
      landed = saves.clock_from_step(int(env._env.get_info().step))
    except (TypeError, ValueError, AttributeError):
      landed = start
    if landed > end:
      return
    _set_action_camera(env, live)
    env._env.game_config.camera_fov = 0.0
    env._env.game_config.render = False
    env._env.set_held(False)
    env._env.set_action_labels(False)
    show, slow_from, _goal = _moment_beats(live.touch_list(), start, end)
    shot, _shot_goal = _scoring_clock(live.touch_list(), start, end)
    scorer = _scorer_identity(live.touch_list(), start, end)
    plate = broadcast.BroadcastPlate(
        panel.get('left_name'),
        panel.get('right_name'),
        broadcast.scorer_card(live.touch_list(), start, end),
        live.clip_language(),
    )
    scorer_mark = _scorer_mark(env, live.touch_list(), start, end)
    load_goal = [_moment_frame_goal(start, end)]
    load_sent = [-1]

    def note_load(written):
      percent, load_goal[0] = moment_load_percent(
          written, load_goal[0], max(0, load_sent[0]))
      if percent == load_sent[0]:
        return
      load_sent[0] = percent
      _publish_moment(
          env, live, 'loading', status=panel, progress=percent / 100.0)

    clip.progress = note_load
    if scorer_mark:
      _set_moment_marks(env, [scorer_mark])
    opening = _draw_picture(env)
    if opening is not None and live.moment_active(token):
      _arm_plate(plate, env, start, show)
      for _ in range(broadcast.OPEN_FRAMES):
        env._env.poll_window(0.0)
        if (
            not live.moment_active(token) or live.quit_requested()
            or _note_escape(env, live)):
          break
        if not clip.write(opening, 1, plate):
          break
    backs = False
    duration = int(env._env.config.game_duration)
    # The step counter stops when the goal is given. The ball keeps moving
    # until the engine puts it back on the center spot. Keep every one of
    # those frames. The next step, the restart, is not drawn.
    tail = 0
    net_state = None
    settle_pose = None
    settle_vel = None
    prev_pose = None
    missed = 0
    clock = start
    nearest = None
    while live.moment_active(token) and not live.quit_requested():
      if _note_escape(env, live):
        break
      step = int(env._env.get_info().step)
      clock = saves.clock_from_step(step)
      ball = _ball_point(env)
      depth = abs(ball[0])
      if clock >= end or depth > _GOAL_LINE:
        tail += 1
        if tail > 150:
          break
      elif step >= duration - 1:
        break
      if (
          scorer_mark is not None
          and clip.written >= _SCORER_MARK_FRAMES):
        _set_moment_marks(env, [])
        scorer_mark = None
      if not backs:
        fire, nearest = _scoring_touch(
            clock, shot, _scorer_distance(env, scorer), nearest)
      else:
        fire = False
      if fire:
        scorer_mark = None
        if not _show_fullbacks(
            env, live, token, clip, plate, clock, show, live.touch_list(),
            start, end):
          break
        backs = True
        _set_action_camera(env, live)
        env._env.game_config.camera_fov = 0.0
        prev_pose = None
      # step() would present the frame when render is on. Keep it off and
      # draw the picture into the video afterwards.
      env._env.game_config.render = False
      before_x = ball[0]
      env._env.step()
      after = _ball_point(env)
      if net_state is not None and _ball_reset(before_x, after[0]):
        break
      image = _draw_picture(env)
      pose = _read_pose(env)
      if pose is not None and prev_pose is not None:
        change = _pose_delta(prev_pose, pose)
        settle_vel = tuple(item / 0.01 for item in change)
        settle_pose = pose
      if pose is not None:
        prev_pose = pose
      if abs(after[0]) > _GOAL_LINE:
        try:
          net_state = _state_blob(env.get_state({}))
        except (TypeError, ValueError, AttributeError):
          pass
        budget = 1.0 / 30.0
      else:
        clock = saves.clock_from_step(int(env._env.get_info().step))
        # The lead-up is one video frame per physics frame. The shot, and
        # the ball in the net, hold each physics frame a little longer.
        if clock >= slow_from:
          budget = 1.0 / 30.0
        else:
          budget = 1.0 / 70.0
      if image is None:
        missed += 1
        if missed == 1:
          print('clip: no frame', flush=True)
        if missed > 8:
          break
        continue
      _arm_plate(plate, env, clock, show)
      if not clip.write(image, _frame_repeats(budget), plate):
        print('clip: encoder failed', flush=True)
        break
    if live.moment_active(token) and not live.home_pending() and net_state is not None:
      _restore_state(env, live, net_state)
      _settle_net(
          env, live, token, clip, plate, clock, show, settle_pose, settle_vel)
    if (
        live.moment_active(token) and not live.home_pending()
        and clip.last is not None):
      _arm_plate(plate, env, clock, show)
      plate.begin_close()
      for _ in range(broadcast.CLOSE_FRAMES):
        if not live.moment_active(token) or live.quit_requested():
          break
        if not clip.write(clip.last, 1, plate):
          break
    clip.close()
    if live.moment_active(token):
      _faststart(path)
    ready = (
        live.moment_active(token)
        and os.path.isfile(path)
        and os.path.getsize(path) > 64)
    if ready and not live.home_pending():
      live.remember_clip(path)
      _publish_moment(
          env, live, 'ready', '/clips/' + os.path.basename(path), panel)
      while (
          live.moment_active(token)
          and not live.clip_finished()
          and not live.quit_requested()
          and not _note_escape(env, live)):
        if live.take_compare():
          _play_compare(env, live, start, end, token, panel)
          break
        env._env.poll_window(0.0)
        time.sleep(0.05)
  finally:
    clip.close()
    _set_moment_marks(env, [])
    env._env.game_config.render = True
    env._env.game_config.reuse_meshes = False
    env._env.game_config.camera_fov = 0.0
    env._env.game_config.camera_focus = 0.0
    try:
      if not live.moment_replaced(token):
        _publish_moment(env, live, 'done', status=panel)
      if not live.home_pending():
        _restore_saved_camera(env, live, saved)
        if live.viewing():
          _scrub_to(env, live, back, force=True)
          if not was_held:
            env._env.set_held(False)
            live.set_frozen(False)
    finally:
      live.clear_clip(path)
      _delete_clip(path)


def _publish_view(env, live):
  status = window_status(env, bool(live.frozen()))
  status['phase'] = 'view' if live.viewing() else 'menu'
  _attach_possession(status, live)
  _attach_timeline(status, live)
  live.publish(None, status)


def _play_branch(env, live, marks, end_clock, progress):
  """Step without drawing until this branch's clock or the full-time whistle."""
  duration = int(env._env.config.game_duration)
  start = int(env._env.get_info().step)
  if end_clock is not None:
    goal = max(start + 1, saves.step_for_clock(int(end_clock)))
    span = max(1, goal - start)
  else:
    span = max(1, duration - max(0, start))
  guard = 0
  last = -1
  while int(env._env.get_info().step) < duration:
    if live.quit_requested():
      return False
    step = int(env._env.get_info().step)
    if end_clock is not None and saves.clock_from_step(step) >= int(end_clock):
      break
    env._env.step()
    guard += 1
    if guard % 40 == 0:
      _note_minute(env, marks, duration)
    done = int(env._env.get_info().step) - start
    percent = min(100, int(max(0, done) * 100 / span))
    if percent != last:
      last = percent
      progress(percent / 100.0)
    # The match window is the main thread. Leave it long enough and the
    # picture stops answering clicks.
    if guard % 8 == 0:
      env._env.poll_window(0.0)
    if guard > span * 2:
      break
  return True


def _remember_base_formation(env, live):
  """Keep the shape the match loaded with. A snapshot does not include it."""
  if not hasattr(env._env, 'read_formation'):
    return
  live.set_base_formation({
      0: formations.pack_entries(env._env.read_formation(0)),
      1: formations.pack_entries(env._env.read_formation(1)),
  })


def _shape_for_line(live):
  """Slots for the line on screen, or the shape the match loaded with."""
  return live.line_formation() or live.base_formation()


def _finish_edit(env, live, restore):
  """Drop an edit. restore puts the picture back to the moment it started from."""
  phase = live.edit_phase()
  origin = live.edit_origin()
  if phase not in ('on', 'ready') and origin is None:
    return
  live.set_edit_origin(None)
  live.set_edit_phase('')
  try:
    env._env.set_editing(False)
    env._env.set_edit_lock(False)
  except AttributeError:
    pass
  if restore:
    _restore_edit_camera(env, live)
  else:
    live.set_edit_view(None)
  if restore and origin is not None:
    _restore_state(env, live, origin)
    _restore_scene(env, live)


def _camera_choice(view):
  choice = {
      'team': int(view[0]),
      'player': int(view[1]),
      'lens': int(view[2]),
  }
  if choice['lens'] == 3:
    choice.update({
        'x': view[3],
        'y': view[4],
        'z': view[5],
        'yaw': view[6],
        'pitch': view[7],
    })
  return choice


def _use_edit_camera(env, live):
  """Fly the picture that is already on screen.

  The cards are off, so the camera panel cannot be reached. The free camera
  keeps that view, and W A S D Q E move it.
  """
  view = _window_camera(env)
  live.set_edit_view(view)
  pose = _read_pose(env)
  if pose is None:
    return
  config = env._env.game_config
  config.camera_team = -1
  config.camera_player = 0
  config.camera_lens = 3
  config.camera_x = pose[0]
  config.camera_y = pose[1]
  config.camera_z = pose[2]
  config.camera_yaw = pose[3]
  config.camera_pitch = pose[4]
  config.camera_fov = 0.0
  config.camera_focus = 0.0
  live.set_camera({
      'team': -1,
      'player': 0,
      'lens': 3,
      'x': pose[0],
      'y': pose[1],
      'z': pose[2],
      'yaw': pose[3],
      'pitch': pose[4],
  })


def _restore_edit_camera(env, live):
  """Put the view back to what it was before the edit."""
  view = live.edit_view()
  live.set_edit_view(None)
  if not view:
    return
  config = env._env.game_config
  config.camera_team = int(view[0])
  config.camera_player = int(view[1])
  config.camera_lens = int(view[2])
  config.camera_x = float(view[3])
  config.camera_y = float(view[4])
  config.camera_z = float(view[5])
  config.camera_yaw = float(view[6])
  config.camera_pitch = float(view[7])
  config.camera_fov = 0.0
  config.camera_focus = 0.0
  live.set_camera(_camera_choice(view))


def _begin_edit(env, live):
  """Hold the picture and let the pointer move players and the ball."""
  if not live.viewing() or not hasattr(env._env, 'set_editing'):
    live.set_edit_phase('')
    return
  if live.edit_view() is None:
    _use_edit_camera(env, live)
  if live.edit_origin() is None:
    live.set_edit_origin(_state_blob(env.get_state({})))
  env._env.game_config.reuse_meshes = False
  env._env.set_editing(True)
  env._env.set_edit_lock(True)
  env._env.set_held(True)
  live.hold_picture()
  live.set_edit_phase('on')
  _publish_view(env, live)


def _cancel_edit(env, live):
  """Put the players back. The match stays held, and nothing is saved."""
  if live.edit_phase() not in ('on', 'ready') and live.edit_origin() is None:
    return
  _finish_edit(env, live, True)
  try:
    env._env.set_held(True)
  except AttributeError:
    pass
  live.hold_picture()
  _publish_view(env, live)


def _commit_edit(env, live):
  """Keep the moved bodies and leave the drag. Play waits for Resume."""
  if live.edit_phase() != 'on':
    return
  try:
    env._env.set_editing(False)
    env._env.set_edit_lock(True)
    env._env.set_held(True)
  except AttributeError:
    return
  live.hold_picture()
  live.set_edit_phase('ready')
  _publish_view(env, live)


def _play_edit_branch(env, live):
  """Save the committed positions as a branch and play from there.

  The formation table is left as the match loaded it. A resume before
  Commit does not come through here.
  """
  if live.edit_phase() != 'ready' or not live.can_branch():
    if live.edit_phase() == 'ready' and not live.can_branch():
      print('Open a simulation first.', flush=True)
    return
  try:
    env._env.config.game_duration = FULL_MATCH_FRAMES
    parent = live.line_id() or None
    base_seed = int(env._env.config.game_engine_random_seed)
    sim_id = live.sim_id()
    branch_id = str(int(live.next_branch_id()))
    step_now = int(env._env.get_info().step)
    clock_now = saves.clock_from_step(step_now)
    seed = _branch_seed(base_seed, int(branch_id), clock_now)
    env._env.reseed(int(seed))
    env._env.clear_touches()
    duration = int(env._env.config.game_duration)
    info = env._env.get_info()
    record = {
        'id': branch_id,
        'parent': parent,
        'clock': clock_now,
        'step': step_now,
        'end_clock': saves.clock_from_step(duration),
        'end_step': duration,
        'minutes': None,
        'score': [int(info.left_goals), int(info.right_goals)],
        'seed': int(seed),
        'marks': [{
            'step': step_now,
            'clock': clock_now,
            'state': _state_blob(env.get_state({})),
        }],
        'touches': [],
        'on_timeline': True,
    }
    record['added'] = _added_players(env)
    saves.write_branch(sim_id, record)
    live.add_branch(record)
    live.set_line(branch_id)
  except (OSError, struct.error, ValueError, AttributeError) as error:
    print('Edit branch was not saved: %s' % error, flush=True)
    live.set_edit_phase('ready')
    try:
      env._env.set_edit_lock(True)
    except AttributeError:
      pass
    _publish_view(env, live)
    return
  live.set_edit_origin(None)
  live.set_edit_phase('')
  env._env.game_config.render = True
  env._env.game_config.reuse_meshes = False
  env._env.set_editing(False)
  env._env.set_edit_lock(False)
  env._env.set_held(False)
  live.set_edit_view(None)
  if int(env._env.game_config.camera_lens) == 3:
    config = env._env.game_config
    live.set_free(config.camera_x, config.camera_y, config.camera_z,
                  config.camera_yaw, config.camera_pitch)
  live.release_picture()
  _restore_scene(env, live)
  live.land_log(env._env.hud_feed().get('clock'))
  _publish_view(env, live)


def _apply_line_formation(env, live):
  """Put the on-screen line's roles back. Bodies stay where the snapshot put them."""
  if not hasattr(env._env, 'apply_formation'):
    return
  shape = _shape_for_line(live)
  if not shape:
    return
  for team, entries in shape.items():
    env._env.apply_formation(int(team), entries, False)


def _run_formation_branch(env, live, sides):
  """Stand the named shapes on the picture and hold.

  The pitch map and the match both show the new positions at once. The
  match does not step. Resume is what plays on from here. The line is saved
  so the original match is still there. The shape is not kept: a later
  restart uses the shape the match loaded with.
  """
  _finish_edit(env, live, True)
  if not live.can_branch() or not hasattr(env._env, 'apply_formation'):
    if not hasattr(env._env, 'apply_formation'):
      print('The match engine has no formation call.', flush=True)
    _publish_view(env, live)
    return
  try:
    env._env.config.game_duration = FULL_MATCH_FRAMES
    parent = live.line_id() or None
    base_seed = int(env._env.config.game_engine_random_seed)
    sim_id = live.sim_id()
    branch_id = str(int(live.next_branch_id()))
    info = env._env.get_info()
    roster = _roster(env, info, [])
    previous = {
        0: formations.pack_entries(env._env.read_formation(0)),
        1: formations.pack_entries(env._env.read_formation(1)),
    }
    for team, name in sides.items():
      team = int(team)
      players = [player for player in roster if int(player['team']) == team]
      placed = formations.assign(name, players, env._env.team_side(team))
      if placed:
        env._env.apply_formation(team, placed, True)
    # Bodies stay where they were just stood. The jobs go back, so a goal
    # or another restart does not stand them in this shape again.
    for team, entries in previous.items():
      if entries:
        env._env.apply_formation(team, entries, False)
    step_now = int(env._env.get_info().step)
    clock_now = saves.clock_from_step(step_now)
    seed = _branch_seed(base_seed, int(branch_id), clock_now)
    env._env.reseed(int(seed))
    env._env.clear_touches()
    duration = int(env._env.config.game_duration)
    info = env._env.get_info()
    record = {
        'id': branch_id,
        'parent': parent,
        'clock': clock_now,
        'step': step_now,
        'end_clock': saves.clock_from_step(duration),
        'end_step': duration,
        'minutes': None,
        'score': [int(info.left_goals), int(info.right_goals)],
        'seed': int(seed),
        'marks': [{
            'step': step_now,
            'clock': clock_now,
            'state': _state_blob(env.get_state({})),
        }],
        'touches': [],
        'on_timeline': True,
    }
    record['added'] = _added_players(env)
    try:
      saves.write_branch(sim_id, record)
      live.add_branch(record)
      live.set_line(branch_id)
    except (OSError, struct.error, ValueError) as error:
      print('Branch was not saved: %s' % error, flush=True)
    env._env.game_config.render = True
    env._env.game_config.reuse_meshes = False
    env._env.set_held(True)
    live.hold_picture()
    _restore_scene(env, live)
    env._env.render(True)
    live.land_log(env._env.hud_feed().get('clock'))
  except Exception as error:
    print('Formation branch failed: %s' % error, flush=True)
    env._env.game_config.render = True
  _publish_view(env, live)


def _run_branches(env, live, count, minutes, seconds=None):
  """Record new matches from the moment on screen. Each one gets a new seed.

  The picture, the players, and the ball stay as they are. The original
  timeline is not rewritten. A pitch edit is the Edit control, not this path.
  """
  count, minutes = _branch_bounds(count, minutes)
  _finish_edit(env, live, True)
  if not live.can_branch() or not hasattr(env._env, 'reseed'):
    if not hasattr(env._env, 'reseed'):
      print('The match engine has no reseed call.', flush=True)
    _publish_view(env, live)
    return
  origin = None
  try:
    env._env.game_config.render = False
    env._env.config.game_duration = FULL_MATCH_FRAMES
    origin = _state_blob(env.get_state({}))
    parent = live.line_id() or None
    base_seed = int(env._env.config.game_engine_random_seed)
    sim_id = live.sim_id()
    first = int(live.next_branch_id())
    for index in range(count):
      if live.quit_requested():
        break
      branch_id = str(first + index)
      _restore_state(env, live, origin)
      step_now = int(env._env.get_info().step)
      clock_now = saves.clock_from_step(step_now)
      seed = _branch_seed(base_seed, int(branch_id), clock_now)
      env._env.reseed(int(seed))
      env._env.clear_touches()
      marks = [{
          'step': step_now,
          'clock': clock_now,
          'state': _state_blob(env.get_state({})),
      }]
      if seconds:
        end_clock = clock_now + int(seconds)
      elif minutes is None:
        end_clock = None
      else:
        end_clock = clock_now + minutes * 60

      def progress(fraction, place=index):
        # A key-moment branch keeps the match page up. The saving status has
        # no timeline, so publishing it removes the band and the overlay.
        if seconds:
          return
        _publish_progress(live, env, (place + fraction) / float(count))

      progress(0.0)
      if not _play_branch(env, live, marks, end_clock, progress):
        break
      progress(1.0)
      info = env._env.get_info()
      end_step = int(info.step)
      record = {
          'id': branch_id,
          'parent': parent,
          'clock': clock_now,
          'step': step_now,
          'end_clock': saves.clock_from_step(end_step),
          'end_step': end_step,
          'minutes': minutes,
          'score': [int(info.left_goals), int(info.right_goals)],
          'seed': int(seed),
          'marks': marks,
          'touches': _touch_rows(env),
      }
      current_shape = live.line_formation()
      if current_shape:
        record['formation'] = current_shape
      if seconds:
        # Kept for a later view. The timeline only draws the other branches.
        record['on_timeline'] = False
      record['added'] = _added_players(env)
      try:
        saves.write_branch(sim_id, record)
        live.add_branch(record)
      except (OSError, struct.error, ValueError) as error:
        print('Branch was not saved: %s' % error, flush=True)
  finally:
    try:
      if origin is not None:
        _restore_state(env, live, origin)
      env._env.clear_touches()
      env._env.game_config.render = True
      env._env.set_held(True)
      live.hold_picture()
      _restore_scene(env, live)
      env._env.render(True)
      live.land_log(env._env.hud_feed().get('clock'))
    except Exception as error:
      print('Could not return to the branch point: %s' % error, flush=True)
      env._env.game_config.render = True
    _publish_view(env, live)


def _clear_branches(env, live):
  """Delete this match's branches and show the match line again."""
  _finish_edit(env, live, True)
  on_branch = bool(live.line_id())
  try:
    clock = saves.clock_from_step(int(env._env.get_info().step))
  except (TypeError, ValueError, AttributeError):
    clock = 0
  sim = live.drop_branches()
  if not sim:
    return
  try:
    saves.clear_branches(sim)
  except OSError as error:
    print('Branches were not cleared: %s' % error, flush=True)
  if on_branch:
    _scrub_to(env, live, clock, force=True)
  _publish_view(env, live)


def _show_line(env, live, line_id):
  """Scrub onto the base match or one branch. Always restore, never continue."""
  if not live.line_exists(line_id):
    return
  # Drop the edit while this line's bodies still match its snapshot.
  _finish_edit(env, live, True)
  if not live.set_line(line_id):
    return
  _apply_line_formation(env, live)
  if line_id:
    _scrub_to(env, live, live.branch_clock(line_id), force=True)
  else:
    step = int(env._env.get_info().step)
    _scrub_to(env, live, saves.clock_from_step(step), force=True)


def _open_save(env, live, sim_id):
  """Play a saved match from the kickoff it was stored at."""
  _finish_edit(env, live, False)
  state = saves.read_simulation(sim_id)
  if not state:
    live.publish(None, {
        'phase': 'menu',
        'open_failed': True,
        'simulations': saves.list_simulations(),
        'fullscreen': bool(env._env.fullscreen()),
    })
    return
  deterministic = False
  for row in saves.list_simulations():
    if row['id'] == sim_id:
      deterministic = bool(row.get('deterministic'))
      break
  timeline = saves.read_timeline(sim_id)
  if _kickoff(env, live, deterministic) is None:
    return
  live.set_sim(sim_id)
  if timeline:
    live.set_timeline(timeline['marks'], timeline['end_clock'])
  live.set_branches(saves.read_branches(sim_id))
  live.set_moments(saves.read_moments(sim_id))
  _begin_view(env, live, state, saves.read_touches(sim_id))


def run_window(env, live):
  """Step the engine on the main thread. The OpenGL window is the picture.

  The overlay owns clicks. This loop still owns the keys and the free-camera
  move, and it does not copy the picture off the GPU. Fullscreen is applied
  once per click, then the published flag is whatever the window actually is,
  including a change from the green button.
  """
  print('Match window open', flush=True)
  next_tick = time.perf_counter()
  reported = next_tick
  previous = next_tick
  last_status = 0.0
  signature = None
  drawn = 0
  try:
    while True:
      if live.quit_requested():
        return
      if _note_escape(env, live):
        pass
      if live.take_home() and live.viewing():
        _return_to_menu(env, live)
        signature = None
        continue
      now = time.perf_counter()
      dt = min(0.05, max(0.0, now - previous))
      previous = now
      if live.take_restart():
        _restart_window_match(env, live)
      picked = live.take_simulate()
      if picked is not None:
        _simulate_and_save(env, live, picked)
      if live.take_clear_branches():
        _clear_branches(env, live)
      branching = live.take_branch()
      if branching is not None:
        if branching[2] is not None:
          _scrub_to(env, live, branching[2], force=True)
        _run_branches(env, live, branching[0], branching[1], branching[3])
      forming = live.take_formation()
      if forming is not None:
        _run_formation_branch(env, live, forming)
      chosen_line = live.take_line()
      if chosen_line is not None:
        _show_line(env, live, chosen_line)
      opened = live.take_open()
      if opened:
        _open_save(env, live, opened)
      removed = live.take_remove_simulation()
      if removed:
        viewing_it = live.viewing() and live.sim_id() == removed
        try:
          saves.delete_simulation(removed)
        except OSError as error:
          print('Simulation was not removed: %s' % error, flush=True)
        if viewing_it:
          _return_to_menu(env, live)
          signature = None
          continue
      choice = live.take_camera_command()
      if choice is not None:
        _apply_overlay_camera(env, choice)
      callouts = live.take_callouts()
      if callouts is not None:
        env._env.set_action_labels(bool(callouts))
      menu = live.take_menu()
      if menu is not None:
        env._env.set_menu_screen(bool(menu))
      boxes = live.take_boxes()
      if boxes is not None:
        env._env.set_boxes(boxes)
      hidden = live.take_hidden()
      if hidden is not None:
        env._env.set_hidden(hidden['players'], bool(hidden['ball']))
      lines = live.take_lines()
      if lines is not None:
        env._env.set_lines(lines)
      freeze = live.take_frozen_command()
      if freeze is not None:
        env._env.set_held(bool(freeze))
      edit_action = live.take_edit()
      if edit_action is not None:
        action, team = edit_action
        if action == 'on':
          _begin_edit(env, live)
        elif action == 'off':
          _cancel_edit(env, live)
        elif action == 'commit':
          _commit_edit(env, live)
        elif action == 'play':
          _play_edit_branch(env, live)
        elif action == 'add':
          try:
            added = env._env.add_edit_player(int(team))
          except AttributeError:
            added = 0
          if added < 0:
            print('That side is full.', flush=True)
        elif action == 'remove':
          try:
            env._env.remove_edit_players()
          except AttributeError:
            pass
        elif action == 'dismiss':
          try:
            env._env.dismiss_add_prompt()
          except AttributeError:
            pass
      scrub = live.take_scrub()
      if scrub is not None:
        _scrub_to(env, live, scrub)
      brief = live.take_brief()
      if brief is not None:
        _open_brief(env, live, brief[0], brief[1], brief[2])
      moment = live.take_moment()
      if moment is not None:
        _play_moment(env, live, moment[0], moment[1], moment[2])
      fullscreen = live.take_fullscreen_command()
      if fullscreen is not None:
        env._env.set_fullscreen(bool(fullscreen))
      band = live.take_bottom_band()
      if band is not None:
        env._env.set_bottom_band(int(band))
      frozen = bool(env._env.poll_window(dt))
      live.note_engine_frozen(frozen)
      camera = _window_camera(env)
      if frozen:
        # Leave the players, the ball, and the clock where they are.
        # Redraw so a camera move stays visible.
        env._env.render(True)
        next_tick = time.perf_counter()
      else:
        env._env.step()
        if int(env._env.get_info().step) >= env._env.config.game_duration:
          _restart_window_match(env, live)
        drawn += 1
        now = time.perf_counter()
        if now - reported >= 10 and drawn:
          print('Match %.0f pictures/sec' % (drawn / (now - reported)),
                flush=True)
          reported = now
          drawn = 0
        next_tick += PHYSICS_FRAME_SECONDS
      status = window_status(env, frozen)
      live.remember(status)
      saved = live.saved_feed()
      if saved is not None:
        status['left'], status['right'] = _feed_from_saved(saved, status['clock'])
      status.pop('roster', None)
      status.pop('ball_meters', None)
      if live.viewing():
        status['phase'] = 'view'
      else:
        status['phase'] = 'menu'
      _attach_timeline(status, live)
      mark = (
          status['frozen'],
          status['fullscreen'],
          status['view']['team'],
          status['view']['player'],
          status['view']['lens'],
          tuple((line['clock'], line['shirt'], line['action'])
                 for line in status['left']),
          tuple((line['clock'], line['shirt'], line['action'])
                 for line in status['right']),
          tuple((round(dot['x'], 3), round(dot['y'], 3), dot['team'])
                for dot in status['dots']),
          None if not status.get('ball') else (
              round(status['ball']['x'], 3),
              round(status['ball']['y'], 3)),
          tuple((row['text'], round(row['x'], 3), round(row['y'], 3))
                for row in status['callouts']),
          int(status.get('span') or 0),
          int(status.get('length') or 0),
          str(status.get('branch') or ''),
          tuple(str(row.get('id') or '') for row in status.get('branches') or []),
          tuple(str(row.get('id') or '') for row in status.get('simulations') or []),
          tuple(sorted(
              (str(key), tuple((int(row.get('start') or 0), int(row.get('end') or 0))
                               for row in rows))
              for key, rows in (status.get('line_moments') or {}).items())),
          str(status.get('edit') or ''),
          bool(status.get('add_prompt')),
      )
      now = time.perf_counter()
      if mark != signature or now - last_status >= 0.1:
        _attach_possession(status, live)
        live.publish(None, status)
        signature = mark
        last_status = now
      if frozen:
        time.sleep(0.016 if camera[2] == 3 else 0.05)
        continue
      remaining = next_tick - time.perf_counter()
      if remaining > 0:
        time.sleep(remaining)
      else:
        next_tick = time.perf_counter()
  finally:
    env.close()


def _overlay_binary():
  folder = os.path.dirname(os.path.abspath(__file__))
  source = os.path.join(folder, 'overlay.swift')
  binary = os.path.join(folder, 'overlay')
  if (not os.path.isfile(binary) or
      os.path.getmtime(source) > os.path.getmtime(binary)):
    subprocess.check_call([
        'swiftc', '-O', '-o', binary, source,
        '-framework', 'Cocoa', '-framework', 'QuartzCore', '-framework', 'WebKit',
    ])
  return binary


def _wait_for_port(port):
  deadline = time.time() + 5
  while time.time() < deadline:
    try:
      with socket.create_connection((HOST, port), 0.2):
        return True
    except OSError:
      time.sleep(0.05)
  return False


def _start_overlay(port):
  binary = _overlay_binary()
  url = 'http://%s:%d/' % (HOST, port)
  return subprocess.Popen([binary, url, str(os.getpid())])


def _wait_for_menu(live):
  """Wait until the menu page has connected. The match window stays hidden."""
  deadline = time.time() + 8
  while time.time() < deadline:
    if live.attached():
      return True
    time.sleep(0.02)
  return False


def main():
  parser = argparse.ArgumentParser(description='Play a GRF match')
  parser.add_argument('--host', default=HOST)
  parser.add_argument('--port', type=int, default=PORT)
  args = parser.parse_args()

  os.environ['BRANCHPLAY_ICON'] = os.path.join(
      os.path.dirname(os.path.abspath(__file__)), 'brand', 'branchplay-icon.png')
  env, configuration = begin_match()
  live = LiveMatch()
  if not window_is_hidden():
    if not os.path.isfile(os.path.join(UI_DIR, 'index.html')):
      raise SystemExit('The match controls are missing. Build viewer/ui first.')
    server = ThreadingHTTPServer((args.host, args.port),
                                  make_handler(live, use_overlay=True))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=pump_status, args=(live,), daemon=True).start()
    if not _wait_for_port(args.port):
      raise SystemExit('The match controls did not start.')
    overlay = _start_overlay(args.port)
    print('Match controls on the game window', flush=True)
    if not _wait_for_menu(live):
      # A dead panel leaves the match with nothing drawn on it. Start it
      # once more before the window is shown.
      if overlay.poll() is not None:
        overlay = _start_overlay(args.port)
      if not _wait_for_menu(live):
        print('Menu page did not connect; opening the match anyway.', flush=True)
    # The action view is already selected. Draw it, then present the window
    # so the loaded menu is the first picture.
    env._env.render(True)
    env._env.show_window()
    env._env.render(True)
    try:
      run_window(env, live)
    finally:
      if overlay.poll() is None:
        overlay.terminate()
    return
  server = ThreadingHTTPServer((args.host, args.port), make_handler(live))
  threading.Thread(target=server.serve_forever, daemon=True).start()
  threading.Thread(target=pump_frames, args=(live,), daemon=True).start()
  print('Play the match at http://%s:%d' % (args.host, args.port), flush=True)
  run_match(env, configuration, live)


if __name__ == '__main__':
  main()
