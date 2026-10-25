"""Bounded player style effects and train-fitted action-frequency intercepts.

Radar-to-style coefficients are explicit hypotheses, not measured causal effects.
Outcome models (pass completion / goal probability) remain separately calibrated.
"""
import json
import math
from pathlib import Path

KINDS = ('pass', 'carry', 'shot')
PATH = Path(__file__).with_name('player-action-profile.json')
CALIBRATION = json.loads(PATH.read_text()) if PATH.exists() else {}
REVISION = 'player-actions-1'
COEFFICIENTS = {
    'pass': {'CRE': .35, 'TAC': .25, 'DEF': .15, 'TEC': .10, 'ATT': -.15},
    'carry': {'TEC': .45, 'ATT': .20, 'TAC': -.15, 'DEF': -.20},
    'shot': {'ATT': .60, 'TEC': .20, 'DEF': -.20},
}


def style_factors(profile, goalkeeper=False, strength=1.0):
    """Missing/conflicting attributes have a neutral multiplier of one."""
    profile = profile or {}
    if (profile.get('status') not in ('complete', 'partial') or
            bool(profile.get('source_conflicts', {}).get('position')) or
            profile.get('attribute_kind') != ('goalkeeper' if goalkeeper else 'outfield')):
        return {k: 1.0 for k in KINDS}
    attributes = profile.get('attributes', {})
    coefficients = ({'pass': {'BAL': .40, 'TAC': .20},
                     'carry': {'BAL': .15, 'ANT': -.20}, 'shot': {}}
                    if goalkeeper else COEFFICIENTS)
    factors = {}
    for kind, weights in coefficients.items():
        effect = 0.0
        for key, weight in weights.items():
            value = attributes.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100:
                effect += weight * (value - 50) / 50
        factors[kind] = math.exp(max(-.6, min(.6, effect * strength)))
    return factors


def adjust_options(options, player, multipliers, strength=1.0):
    """Adjust only legal candidates; class size never multiplies its prior."""
    factors = style_factors(player.get('sofascore'), player['number'] == 1, strength)
    for option in options:
        kind = option['kind']
        option['weight'] *= multipliers.get(kind, 1.0) * factors[kind]
    total = sum(o['weight'] for o in options)
    if not math.isfinite(total) or total <= 0:
        raise ValueError('Action weights must have positive finite mass')
    for option in options:
        option['probability'] = option['weight'] / total
    return options
