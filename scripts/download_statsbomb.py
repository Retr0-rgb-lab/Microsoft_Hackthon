"""Download StatsBomb open-data matches on purpose.

Reads only https://github.com/statsbomb/open-data raw files. Tests do not
run this script. The default output directory is ``data/statsbomb/<match_id>``,
which is gitignored. The match checked into ``fixtures/statsbomb/`` was
produced with ``--output``.

Examples
--------
List matches in a competition season::

    python scripts/download_statsbomb.py --list --competition-id 72 --season-id 30

Download one match (Women's World Cup 2019 semi-final)::

    python scripts/download_statsbomb.py --competition-id 72 --season-id 30 --match-id 69284

Write the slimmed files somewhere else::

    python scripts/download_statsbomb.py --competition-id 72 --season-id 30 \\
        --match-id 69284 --output fixtures/statsbomb/69284
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inside_the_game.ingest.statsbomb import project_event, project_match  # noqa: E402


OPEN_DATA = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
USER_AGENT = "inside-the-game-statsbomb-open-data"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fetch StatsBomb open-data matches.")
    parser.add_argument("--competition-id", type=int, required=True)
    parser.add_argument("--season-id", type=int, required=True)
    parser.add_argument("--match-id", type=int)
    parser.add_argument(
        "--output",
        type=Path,
        help="Directory for match.json and events.json. Default: data/statsbomb/<match_id>.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print matches in the competition season and exit.",
    )
    args = parser.parse_args(argv)
    matches = _get_json(f"{OPEN_DATA}/matches/{args.competition_id}/{args.season_id}.json")
    if not isinstance(matches, list):
        raise SystemExit("matches payload was not a list")
    if args.list or args.match_id is None:
        for match in matches:
            home = match["home_team"]["home_team_name"]
            away = match["away_team"]["away_team_name"]
            stage = match["competition_stage"]["name"]
            print(f"{match['match_id']}\t{match['match_date']}\t{home} vs {away}\t{stage}")
        return
    selected = next((match for match in matches if match["match_id"] == args.match_id), None)
    if selected is None:
        raise SystemExit(
            f"match {args.match_id} is not in competition {args.competition_id} season {args.season_id}"
        )
    events = _get_json(f"{OPEN_DATA}/events/{args.match_id}.json")
    if not isinstance(events, list):
        raise SystemExit("events payload was not a list")
    destination = args.output or (ROOT / "data" / "statsbomb" / str(args.match_id))
    destination.mkdir(parents=True, exist_ok=True)
    match_path = destination / "match.json"
    events_path = destination / "events.json"
    projected_match = project_match(selected)
    match_path.write_text(json.dumps(projected_match, indent=2) + "\n", encoding="utf-8")
    projected = [project_event(event) for event in events]
    events_path.write_text(json.dumps(projected, separators=(",", ":")) + "\n", encoding="utf-8")
    notice = destination / "SOURCE.txt"
    notice.write_text(_source_note(projected_match, len(projected)), encoding="utf-8")
    print(f"wrote {match_path}")
    print(f"wrote {events_path} ({len(projected)} events)")
    print(f"wrote {notice}")


def _source_note(match: dict, event_count: int) -> str:
    home = match["home_team"]["name"]
    away = match["away_team"]["name"]
    return (
        f"Match {match['match_id']}, {match.get('competition')} {match.get('season')}, "
        f"{match.get('competition_stage')}\n"
        f"{home} {match.get('home_score')}–{match.get('away_score')} {away}"
        f" ({match.get('match_date')})\n"
        f"{event_count} events, reduced to the fields this repository reads.\n"
        "Source: StatsBomb Open Data https://github.com/statsbomb/open-data\n"
        "License: Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)\n"
        "https://creativecommons.org/licenses/by-nc/4.0/\n"
        "Commercial use of this file needs separate permission from StatsBomb.\n"
    )


def _get_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
