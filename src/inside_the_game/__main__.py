"""Run the offline MVP stub on the synthetic fixture."""

from __future__ import annotations

from inside_the_game.pipeline import run_mvp
from inside_the_game.present.overlay import format_overlay


def main() -> None:
    frames = run_mvp()
    for frame in frames:
        print(format_overlay(frame.overlay))
        print()


if __name__ == "__main__":
    main()
