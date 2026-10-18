#!/usr/bin/env bash
# Startet ComfyUI headless auf 127.0.0.1:8188.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d ComfyUI ] || { echo "ComfyUI fehlt. Zuerst scripts/install_comfyui.sh ausführen."; exit 1; }
# shellcheck disable=SC1091
source ComfyUI/.venv/bin/activate
cd ComfyUI
exec python main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch
