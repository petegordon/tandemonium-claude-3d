#!/usr/bin/env bash
# Optional: Instant Meshes (wjakob, BSD) for `retopo_bake.py --remesher instant`.
set -euo pipefail
dir="$(cd "$(dirname "$0")/.." && pwd)/tools/instant-meshes"
mkdir -p "$dir" && cd "$dir"
curl -sSL -o im.zip https://instant-meshes.s3.eu-central-1.amazonaws.com/Release/instant-meshes-windows.zip
unzip -o im.zip && rm im.zip
ls -la "$dir"
