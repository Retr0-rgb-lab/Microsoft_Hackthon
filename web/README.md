# Scheme A shell

On-ball decision screen for Inside the Game. The left side is the video stage and the possession timeline. The right side is only the softmax distribution, two short explains, one System 2 line, the mini pitch, and the decision-aid disclaimer.

This is not a league portal. There is no table, squad wall, fixture list, or season map.

The shell does not change the softmax, the possession state machine, or team assignment. Those stay in the Python demo. Sidebar numbers come from `public/scheme-a.json` until a live payload replaces that file.

## Run

From this directory:

```bash
npm install
npm run dev
```

Open the URL Vite prints, usually http://127.0.0.1:5173.

```bash
npm test
npm run build
```

## Load a preview video

The stage draws a placeholder pitch until you give it a file. Arrows on that plate are the shell overlay: a bright yellow primary, then the limited secondaries below.

Render a clip from the repository root when you want a real broadcast under the chrome:

```bash
python -m demo.run \
  --input data/clips/08fd33_0.mp4 \
  --output preview_08fd33_10s.mp4 \
  --seconds 10 \
  --stride 2
```

Then either:

- Use the folder button in the shell and choose that mp4, or
- Copy it to `web/public/preview.mp4` and reload. The shell requests `/preview.mp4` on startup.
- Or open `http://127.0.0.1:5173/?video=/preview.mp4`.

`web/public/preview.mp4` is gitignored. Do not commit match footage.

The timeline is match clock (90:00 in the fixture). Seeking it moves a loaded file proportionally across that file's duration. The sidebar follows the key-possession marks in the JSON, not detector output inside the file.

A `demo.run` mp4 already has the pipeline arrow burned in. The shell still paints its own fixture arrows, so both layers show. Point the stage at the clean source clip when you want the shell arrow to be the only one.

## Sidebar contract

`public/scheme-a.json` is fetched at load. Replace that file and refresh. No rebuild.

```json
{
  "schema_version": 1,
  "title": "Inside the Game",
  "scheme": "Scheme A",
  "duration_seconds": 5400,
  "initial_moment_id": "m6322",
  "disclaimer": "Decision aid. This is the full distribution over pass, shoot, dribble, and hold — not a single optimal action.",
  "moments": []
}
```

Each moment:

| Field | Meaning |
| --- | --- |
| `id` | Stable id. The timeline button uses it. |
| `t_seconds` | Match clock, seconds from kickoff. |
| `recommended` | `pass`, `shoot`, `dribble`, or `hold`. This is the display primary (green bar, and the arrow class). It is not an optimality flag. |
| `distribution` | All four keys, each ≥ 0, sum within 0.001 of 1. The shell prints every share as a percent. |
| `primary_explain` | Short line for the highlighted class. |
| `secondary_explain` | Short line for the spare **pass**. The shell rejects a line that does not mention a pass, and rejects any line that mentions hold. |
| `system2_rationale` | One line. |
| `players` | One possessor. `frame` is 0–1 on the video (origin top-left). `pitch` is meters, x 0–105 toward the goal home attacks, y 0–68. |
| `arrows` | Candidates. The shell then applies the display rules below. |

Display rules, even when the payload has more geometry:

- **Pass:** solid yellow primary, then at most two translucent secondary passes.
- **Dribble:** dashed yellow carry, then at most one translucent secondary pass. A second carry is dropped.
- **Shoot and hold:** probability bars only. No field arrow and no minimap arrow.
- The primary arrow is `#FFE500`. Sidebar green `#00FF85` is only the highlighted softmax row.

Dot colors on the placeholder are fixture paint so the plate can be read. Home and away box coloring stays a computer-vision concern and is not part of this shell.
