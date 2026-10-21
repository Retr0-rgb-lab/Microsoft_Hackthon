# Source

Imported from [LiNTe912/NextPlay-AI](https://github.com/LiNTe912/NextPlay-AI) without forking that repository and without its git history.

| Field | Value |
| --- | --- |
| Source repository | https://github.com/LiNTe912/NextPlay-AI |
| Source commit | `a964c71031b0f32a8ed5226d77db5ce24f16e2b4` |
| Source commit date | 2026-10-21 11:45:17 +0100 |
| Import date | 2026-10-21 |
| Original license | None. This commit has no `LICENSE` file, and the GitHub repository metadata reports `license: null`. No SPDX license was copied because none was published. |
| Authorization | The author LiNTe912 granted permission to use this code in this hackathon project. |

The working tree at that commit was copied into `touchline/`. Measured sizes at import:

| Tree | Bytes |
| --- | --- |
| Clone directory, including `.git` | 395,434,459 (about 377 MiB; `du -sh` prints this as 378M) |
| `data/` only | 335,759,796 (about 320 MiB; `du -sh` prints this as 321M) |
| Working tree excluding `.git` | 336,099,646 |

`data/` was not copied wholesale. The checked-in sample is the legacy Harbor FC vs Mountain FC match without `tracking.jsonl`, the Northwater League index for four matchweeks, and two match directories (`NW26-W01-THF-HBR` and `NW26-W03-ASH-MTN`) without full tracking. See the size note in the pull request for the trimmed total.

## Name replacement

Upstream code, UI copy, and `data/league/squads.json` identified 20 real 2026/27 clubs, their grounds, and 566 real players (names, shirt numbers, nationalities, dates of birth, and external player ids). That squad file was not imported. Shipped JSON, JSONL, code, and UI strings use the fictional identities below. A scan of this tree against the upstream squad file found no remaining full player names, club names, or stadium names outside this document.

`generate.py` now builds 560 procedural players (28 per club). Full names are `{Given} {Family}` pairs from fixed lists in that file. Nationalities and dates of birth are procedural. There is no per-player mapping, so real player names are not repeated here.

Kit colours in `CLUBS` are a new palette. They are not the upstream club colour values.

The numeric strength multipliers moved with the slot in the table below. They are still compressed heuristics. They are not official ratings.

| Slot | Upstream id | Upstream club | Upstream ground | Fictional id | Fictional club | Fictional ground |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | ARS | Arsenal | Emirates Stadium | HBR | Harbor FC | Harbor Park |
| 2 | AVL | Aston Villa | Villa Park | MTN | Mountain FC | Mountain Ground |
| 3 | BOU | AFC Bournemouth | Vitality Stadium | RVD | Riverdale Athletic | Riverdale Bowl |
| 4 | BRE | Brentford | Gtech Community Stadium | CDR | Cedar United | Cedar Lane |
| 5 | BHA | Brighton & Hove Albion | Amex Stadium | BRK | Bracken Town | Bracken Field |
| 6 | CHE | Chelsea | Stamford Bridge | WLN | Welland City | Welland Gate |
| 7 | COV | Coventry City | CBS Arena | NQY | Northquay | Northquay Park |
| 8 | CRY | Crystal Palace | Selhurst Park | SLM | Saltmere | Saltmere Ground |
| 9 | EVE | Everton | Hill Dickinson Stadium | OKR | Oakmere Rovers | Oakmere Park |
| 10 | FUL | Fulham | Craven Cottage | FNB | Fenharbor | Fen Gate |
| 11 | HUL | Hull City | MKM Stadium | KST | Kestrel Athletic | Kestrel Moor |
| 12 | IPS | Ipswich Town | Portman Road | LNT | Lantern FC | Lantern Yard |
| 13 | LEE | Leeds United | Elland Road | DSK | Duskford | Duskford Arena |
| 14 | LIV | Liverpool | Anfield | PEL | Pelican Town | Pelican Wharf |
| 15 | MCI | Manchester City | Etihad Stadium | ASH | Ashcombe | Ashcombe Park |
| 16 | MUN | Manchester United | Old Trafford | VLM | Vellum United | Vellum Street |
| 17 | NEW | Newcastle United | St James' Park | CRC | Coracle FC | Coracle Dock |
| 18 | NFO | Nottingham Forest | City Ground | YRW | Yarrow Athletic | Yarrow Field |
| 19 | SUN | Sunderland | Stadium of Light | GLN | Glenwick | Glenwick Park |
| 20 | TOT | Tottenham Hotspur | Tottenham Hotspur Stadium | THF | Thornferry | Thornferry End |

Competition id `PL-SYN-2026` / name `Premier League (synthetic)` became `NW-SYN-2026` / `Northwater League (synthetic)`. Match ids use the prefix `NW26` instead of `PL26`.

Harbor FC and Mountain FC were already the upstream legacy two-team example. They are reused as the first two fictional league clubs. The legacy single match still uses team ids `HOME` and `AWAY` and names such as `Harbor Player 01`.

`tests/post-match-report-preview.png` was removed. It was an upstream screenshot of a report that named real clubs and players, including Manchester City, Brentford, and Erling Haaland. No test referenced the file.

## Not replaced

- Optional narration still targets the OpenAI Responses API (`https://api.openai.com/v1`, mode `openai`, environment variables `OPENAI_API_KEY` and `OPENAI_MODEL`) in `model_service.py`, `server.py`, `analysis_agent.py`, and the settings form in `index.html`. Those strings name the third-party service. They are not club, player, or competition identities.
- Fictional players are assigned real country names as nationalities (for example Norway, Portugal, Ghana). Those are countries, not copied player biographies.
- Kick-off times use the IANA zone `Europe/London`.
- `analysis_agent.py` still says the demo impact score is "not an official rating." That sentence does not name a competition.

## Regenerate

From `touchline/`:

```sh
python3 generate.py --weeks 4 --tracking none --retain-matches 2
python3 generate.py --mode single --output data
```

`--retain-matches` simulates every fixture, writes the league index, and then keeps the week-1 opener and the week-3 featured match (the explorer default when no home club is selected). Omit the flag to keep all match directories. `tracking.jsonl` and `data/league-alt/` are gitignored. Details are in `README.md`.
