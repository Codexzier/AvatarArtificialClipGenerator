#!/usr/bin/env python3
"""Lädt die Modelle für Wan 2.2 S2V nach ComfyUI/models/. Ohne --yes wird nur aufgelistet."""
import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config, resolve_path

WAN22 = "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files"
WAN21 = "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files"
# (Ordner, Datei, URL, Größe in GB laut Vorlage, Lizenz)
MODELS = {
    "unet": ("diffusion_models", "wan2.2_s2v_14B_fp8_scaled.safetensors", f"{WAN22}/diffusion_models/wan2.2_s2v_14B_fp8_scaled.safetensors", 15.27, "Apache-2.0"),
    "clip": ("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors", f"{WAN21}/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", 6.27, "Apache-2.0"),
    "vae": ("vae", "wan_2.1_vae.safetensors", f"{WAN22}/vae/wan_2.1_vae.safetensors", 0.24, "Apache-2.0"),
    "audio": ("audio_encoders", "wav2vec2_large_english_fp16.safetensors", f"{WAN22}/audio_encoders/wav2vec2_large_english_fp16.safetensors", 0.60, "Apache-2.0"),
    "lora": ("loras", "wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors", f"{WAN22}/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors", 1.2, "Apache-2.0 (Größe geschätzt)"),
    # Video -> Video (Wan 2.2 Fun Control 5B); Größen laut offizieller ComfyUI-Vorlage
    "fun5b": ("diffusion_models", "wan2.2_fun_control_5B_bf16.safetensors", f"{WAN22}/diffusion_models/wan2.2_fun_control_5B_bf16.safetensors", 9.32, "Apache-2.0"),
    "vae22": ("vae", "wan2.2_vae.safetensors", f"{WAN22}/vae/wan2.2_vae.safetensors", 1.31, "Apache-2.0"),
}
SETS = {"s2v": ["unet", "clip", "vae", "audio", "lora"], "v2v": ["fun5b", "vae22", "clip"]}


def download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    start = tmp.stat().st_size if tmp.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-"} if start else {})
    with urllib.request.urlopen(req) as r, open(tmp, "ab" if start and r.status == 206 else "wb") as f:
        got = start if r.status == 206 else 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            got += len(chunk)
            print(f"\r  {got / 1e9:6.2f} GB", end="", flush=True)
    tmp.rename(dest)
    print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("parts", nargs="*", choices=list(MODELS), help="leer = alle")
    p.add_argument("--set", choices=list(SETS), help="s2v = sprechendes Bild, v2v = Video→Video")
    p.add_argument("--yes", action="store_true")
    a = p.parse_args()
    keys = a.parts or (SETS[a.set] if a.set else list(MODELS))
    root = resolve_path(load_config()["paths"]["comfyui_dir"]) / "models"
    total = 0.0
    for k in keys:
        folder, name, _, gb, lic = MODELS[k]
        have = (root / folder / name).exists()
        total += 0 if have else gb
        print(f"  {name:<62} {gb:5.2f} GB  {lic}{'  [vorhanden]' if have else ''}")
    print(f"Noch zu laden: ca. {total:.1f} GB")
    if not a.yes:
        print("Zum Herunterladen mit --yes erneut starten.")
        return
    for k in keys:
        folder, name, url, *_ = MODELS[k]
        if not (root / folder / name).exists():
            print("Lade", name)
            download(url, root / folder / name)


if __name__ == "__main__":
    main()
