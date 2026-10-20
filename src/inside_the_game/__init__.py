"""Inside the Game.

Events path: ingest, System 1, System 2, text overlay (``python -m inside_the_game``).
Video path: ``python -m demo.run`` paints that same softmax on a broadcast clip.
"""

from inside_the_game.labels import ACTION_LABELS
from inside_the_game.pipeline import run_mvp

__all__ = ["ACTION_LABELS", "run_mvp"]
__version__ = "0.1.0"
