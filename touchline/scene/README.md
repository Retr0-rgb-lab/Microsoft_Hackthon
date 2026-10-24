# Pitch sample

Vite + three.js view of the synthetic 25 Hz clip. Twenty-two capsules, a ball, a broadcast camera, and a top-down camera. This is the 3D scene sample only. It is not the league dashboard and it does not draw a possession decision overlay.

The locked coordinate system is in [`../scripts/synth/FORMAT.md`](../scripts/synth/FORMAT.md). Data `(x, y, z)` maps to three.js `Vector3(x, z, -y)`. `rotation.y` is the data facing.

## Run

From this directory:

```sh
npm install
npm run dev
```

Open http://127.0.0.1:5174 . The dev server is pinned to port 5174 so it does not take the Touchline dashboard port.

The decision flow is [flow.html](flow.html) on the same server: http://127.0.0.1:5174/flow.html . It pauses this clip on `decision_point` events and shows a softmax HUD. The state machine is in [FLOW.md](FLOW.md).

`npm test` checks the coordinate mapping and that the short clip has 22 players. `npm run build` typechecks and writes `dist/`.

## Clip

The page loads [`../data/samples/sample_25hz_10min/clip.jsonl`](../data/samples/sample_25hz_10min/clip.jsonl): frames 0–750, `t_ms` 0–30000, 25 Hz (about 30 seconds). That file is what `npm run dev` plays, so the first load stays small.

The full 10-minute file is the checked-in `tracking.jsonl` in the same folder (15001 frames, about 17 MB). Open:

```text
http://127.0.0.1:5174/?clip=tracking.jsonl
```

Other query flags:

| Flag | Meaning |
| --- | --- |
| `?t=20.32` | Start at 20.32 s (a lofted pass in the short clip, ball z = 1.8 m) |
| `?pause=1` | Hold that time |
| `?cam=top` | Open on the top-down camera |
| `?cam=broadcast` | Open on the broadcast camera (the default) |

Buttons: **转播** (broadcast) and **俯视** (top-down). Keys: `1` / `b`, `2` / `t`. Space pauses.

HOME and AWAY are flat kit colours for the sample. The page does not print club or player names from the metadata.
