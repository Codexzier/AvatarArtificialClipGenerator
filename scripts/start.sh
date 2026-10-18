#!/usr/bin/env bash
# Startet ComfyUI (Hintergrund) und die App. Beenden mit Strg+C beendet beides.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .work
if curl -fs http://127.0.0.1:8188/system_stats >/dev/null; then
  echo "ComfyUI läuft bereits."
else
  scripts/start_comfyui.sh > .work/comfyui.log 2>&1 &
  COMFY_PID=$!
  trap 'kill $COMFY_PID 2>/dev/null || true' EXIT
  echo "Starte ComfyUI (Log: .work/comfyui.log) ..."
  for _ in $(seq 1 120); do
    curl -fs http://127.0.0.1:8188/system_stats >/dev/null && break
    kill -0 $COMFY_PID 2>/dev/null || { echo "ComfyUI wurde beendet, siehe .work/comfyui.log"; exit 1; }
    sleep 2
  done
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m app.main
