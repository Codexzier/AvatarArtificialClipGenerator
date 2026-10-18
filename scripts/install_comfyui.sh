#!/usr/bin/env bash
# Installiert ComfyUI (eigene venv, PyTorch mit CUDA) und optional ComfyUI-GGUF.
# Download: ComfyUI ca. 50 MB, PyTorch + Abhängigkeiten ca. 3-4 GB.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || echo "WARNUNG: nvidia-smi nicht gefunden"
[ -d ComfyUI ] || git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
# cu128 deckt RTX 40xx ab; bei Problemen die aktuelle Zeile auf pytorch.org prüfen.
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
if [ "${WITH_GGUF:-0}" = "1" ]; then
  [ -d custom_nodes/ComfyUI-GGUF ] || git clone --depth 1 https://github.com/city96/ComfyUI-GGUF custom_nodes/ComfyUI-GGUF
  pip install -r custom_nodes/ComfyUI-GGUF/requirements.txt
fi
python -c "import torch; print('CUDA verfügbar:', torch.cuda.is_available(), torch.version.cuda)"
