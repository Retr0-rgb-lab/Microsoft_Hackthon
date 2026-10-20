"""Write a labeled synthetic fixture. Fully offline.

Example::

    python scripts/generate_synthetic.py --output fixtures/synthetic_labeled_sequences.json --seed 7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inside_the_game.ingest.synthetic import DEFAULT_CYCLES, DEFAULT_SEED, write_fixture  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Emit labeled synthetic match events.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "fixtures" / "synthetic_labeled_sequences.json",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--cycles", type=int, default=DEFAULT_CYCLES)
    args = parser.parse_args(argv)
    path = write_fixture(args.output, seed=args.seed, cycles=args.cycles)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
