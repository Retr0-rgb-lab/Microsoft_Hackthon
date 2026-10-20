#!/usr/bin/env bash
# Download the two broadcast clips used by the video demo.
# Research / non-commercial. Do not commit the mp4 files.
# Source: roboflow/sports sample downloads of DFL Bundesliga tactical-camera clips.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$root/data/clips"
cd "$root/data/clips"
gdown 1OG8K6wqUw9t7lp9ms1M48DxRhwTYciK- -O 08fd33_0.mp4
gdown 19PGw55V8aA6GZu5-Aac5_9mCy3fNxmEf -O 2e57b9_0.mp4
ls -lh
