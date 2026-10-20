"""Inside the Game MVP scaffold.

Path: ingest synthetic events, System 1 action distribution, System 2
explanation, replay overlay. Computer vision is out of scope.
"""

from inside_the_game.labels import ACTION_LABELS
from inside_the_game.pipeline import run_mvp

__all__ = ["ACTION_LABELS", "run_mvp"]
__version__ = "0.1.0"
