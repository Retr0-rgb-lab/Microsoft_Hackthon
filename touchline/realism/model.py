"""Small smoothed frequency models fitted on training matches only."""
import json
import math
from pathlib import Path

PROFILE = Path(__file__).with_name('profile.json')

def bucket(distance):
    return min(4, int(distance // 10))

def shot_bucket(x, y):
    distance = math.hypot(105-x, y-34)
    return min(4, int(distance // 8))

def probability(table, key, fallback):
    row = table.get(str(key))
    return row['probability'] if row else fallback

class Model:
    def __init__(self):
        self.profile = json.loads(PROFILE.read_text()) if PROFILE.exists() else {}

    def pass_success(self, distance, pressured):
        return probability(self.profile.get('pass_success', {}),
                           f'{bucket(distance)}:{int(pressured)}', .88-.007*distance-.08*pressured)

    def shot_goal(self, x, y):
        return probability(self.profile.get('shot_goal', {}), shot_bucket(x, y),
                           max(.015, .35*math.exp(-math.hypot(105-x, y-34)/15)))

    def action_weights(self, x):
        row = self.profile.get('actions', {}).get(str(min(3, int(x//26.25))))
        return row or {'pass': .65, 'carry': .30, 'shot': .05}
