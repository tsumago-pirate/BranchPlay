"""Languages for a key moment.

The choice is made before the article, the key-moment video, or the
counterfactual is generated. The same choice is used for all three.
Player names stay as they are in the log. These are the fixed words.
The paragraph itself is written by the model in the chosen language.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

LANGUAGES = ('en', 'es', 'fr', 'pt', 'de')

NAMES = {
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'pt': 'Portuguese',
    'de': 'German',
}

# Fixed words. The model is not asked to invent these.
_PHRASES = {
    'en': {
        'key_moment': 'Key moment',
        'key_moment_card': 'KEY MOMENT',
        'what_if': 'WHAT IF',
        'what_if_title': 'What if',
        'reality': 'REALITY',
        'reality_short': 'REALITY',
        'alternate_outcome': 'ALTERNATE OUTCOME',
        'alternate_short': 'ALTERNATE',
        'minute': "MIN. %d'",
        'own_goal': 'Own goal',
        'own_goal_name': 'Own goal, %s',
        'goal_name': "%s's goal",
        'goal_side': '%s goal',
        'empty': 'No action in this stretch is in the log.',
    },
    'es': {
        'key_moment': 'Momento clave',
        'key_moment_card': 'MOMENTO CLAVE',
        'what_if': 'Y SI',
        'what_if_title': 'Y si',
        'reality': 'REALIDAD',
        'reality_short': 'REALIDAD',
        'alternate_outcome': 'DESENLACE ALTERNATIVO',
        'alternate_short': 'ALTERNATIVA',
        'minute': "MIN. %d'",
        'own_goal': 'Gol en propia',
        'own_goal_name': 'Gol en propia, %s',
        'goal_name': 'Gol de %s',
        'goal_side': 'Gol de %s',
        'empty': 'No hay ninguna acción de este tramo en el registro.',
    },
    'fr': {
        'key_moment': 'Moment clé',
        'key_moment_card': 'MOMENT CLÉ',
        'what_if': 'ET SI',
        'what_if_title': 'Et si',
        'reality': 'RÉALITÉ',
        'reality_short': 'RÉALITÉ',
        'alternate_outcome': 'ISSUE AUTRE',
        'alternate_short': 'AUTRE',
        'minute': "MIN. %d'",
        'own_goal': 'But contre son camp',
        'own_goal_name': 'But contre son camp, %s',
        'goal_name': 'But de %s',
        'goal_side': 'But de %s',
        'empty': "Aucune action de ce passage n'est dans le journal.",
    },
    'pt': {
        'key_moment': 'Momento-chave',
        'key_moment_card': 'MOMENTO-CHAVE',
        'what_if': 'E SE',
        'what_if_title': 'E se',
        'reality': 'REALIDADE',
        'reality_short': 'REALIDADE',
        'alternate_outcome': 'DESFECHO ALTERNATIVO',
        'alternate_short': 'ALTERNATIVA',
        'minute': "MIN. %d'",
        'own_goal': 'Autogolo',
        'own_goal_name': 'Autogolo, %s',
        'goal_name': 'Golo de %s',
        'goal_side': 'Golo de %s',
        'empty': 'Não há ação deste lance no registo.',
    },
    'de': {
        'key_moment': 'Schlüsselszene',
        'key_moment_card': 'SCHLÜSSELSZENE',
        'what_if': 'WAS WÄRE WENN',
        'what_if_title': 'Was wäre wenn',
        'reality': 'REALITÄT',
        'reality_short': 'REALITÄT',
        'alternate_outcome': 'ANDERER VERLAUF',
        'alternate_short': 'ALTERNATIVE',
        'minute': "MIN. %d'",
        'own_goal': 'Eigentor',
        'own_goal_name': 'Eigentor, %s',
        'goal_name': 'Tor von %s',
        'goal_side': 'Tor von %s',
        'empty': 'In diesem Abschnitt steht keine Aktion im Protokoll.',
    },
}


def normalize(language):
  """One of the five languages. Anything else is English."""
  text = str(language or '').strip().lower()
  if text in _PHRASES:
    return text
  if len(text) >= 2 and text[:2] in _PHRASES:
    return text[:2]
  return 'en'


def phrase(language, key):
  """A fixed word for this language. English fills a missing key."""
  code = normalize(language)
  table = _PHRASES[code]
  if key in table:
    return table[key]
  return _PHRASES['en'][key]


def name(language):
  return NAMES[normalize(language)]
