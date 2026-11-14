"""Ausgabebilder eines ComfyUI-Laufs (SaveImage) herunterladen."""
import shutil
from pathlib import Path

from app.comfy.client import ComfyClient, output_files


def download_frames(client: ComfyClient, history: dict, frames_dir: Path) -> int:
    """Speichert alle Ausgabebilder als frame_00001.png ... und gibt die Anzahl zurück."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    files = output_files(history)
    if not files:
        raise RuntimeError("ComfyUI hat keine Bilder geliefert.")
    for i, f in enumerate(files, 1):
        data = client.view(f["filename"], f.get("subfolder", ""), f.get("type", "output"))
        (frames_dir / f"frame_{i:05d}.png").write_bytes(data)
    return len(files)


def cleanup_comfy_output(comfyui_dir: Path | None, prefix: str) -> None:
    """Entfernt die Zwischenbilder eines Jobs aus ComfyUI/output."""
    if comfyui_dir:
        shutil.rmtree(comfyui_dir / "output" / Path(prefix).parent, ignore_errors=True)
