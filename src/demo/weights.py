"""Local paths for the pinned Hugging Face football weights."""

from __future__ import annotations

import urllib.request
from pathlib import Path


HF_MODELS: dict[str, tuple[str, str]] = {
    "player": (
        "yolo-football-player-detection.pt",
        "https://huggingface.co/martinjolif/yolo-football-player-detection/resolve/main/yolo-football-player-detection.pt",
    ),
    "ball": (
        "yolo-football-ball-detection.pt",
        "https://huggingface.co/martinjolif/yolo-football-ball-detection/resolve/main/yolo-football-ball-detection.pt",
    ),
    "pitch": (
        "yolo-football-pitch-detection.pt",
        "https://huggingface.co/martinjolif/yolo-football-pitch-detection/resolve/main/yolo-football-pitch-detection.pt",
    ),
}


def ensure_weights(models_dir: Path) -> dict[str, Path]:
    """Return local ``.pt`` paths, downloading a missing file from Hugging Face."""
    models_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for key, (filename, url) in HF_MODELS.items():
        path = models_dir / filename
        if not path.is_file() or path.stat().st_size < 1_000_000:
            _download(url, path)
        paths[key] = path
    return paths


def _download(url: str, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": "inside-the-game-demo"})
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    temporary.replace(path)
