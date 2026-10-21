# sample_25hz_10min

Synthetic 25 Hz tracking clip (10 minutes in the full file, centre-origin metres). The bundle is described in [`../README.md`](../README.md). Schema and the three.js axis map are in [`../../../scripts/synth/FORMAT.md`](../../../scripts/synth/FORMAT.md).

| File | Role |
| --- | --- |
| `metadata.json` | `frame_hz` 25, 22 players, column layout |
| `clip.jsonl` | **Demo clip.** Frames 0–750 (`t_ms` 0–30000). This is what the pitch scene plays by default. |
| `tracking.jsonl` | Full match, 15001 frames, about 17 MB. Checked in. |
| `events.jsonl`, `states.jsonl`, `summary.json`, `validation_report.json` | Rest of the sample bundle. The 3D scene does not read them. |

Point the scene at the full file:

```text
http://127.0.0.1:5174/?clip=tracking.jsonl
```

Run the viewer from [`../../../scene`](../../../scene) (`npm run dev`).
