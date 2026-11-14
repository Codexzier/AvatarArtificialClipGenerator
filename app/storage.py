"""Schritt 6: Ergebnisordner outputs/<Datum_Uhrzeit>/ anlegen."""
import json
import re
import shutil
import time
from pathlib import Path


def safe_name(name: str, default: str = "video") -> str:
    """Dateiname ohne Pfad und Sonderzeichen (ohne Endung)."""
    name = re.sub(r"\.(mp4|wav)$", "", (name or "").strip(), flags=re.I)
    name = re.sub(r"[^\w\- äöüÄÖÜß]+", "_", name).strip(" _.")
    return name[:80] or default


def save_run(outputs_dir: Path, video: Path, wav: Path, image: Path, settings: dict, name: str = "video") -> Path:
    """Legt outputs/<Datum_Uhrzeit>[_<name>]/ an; das Video heißt <name>.mp4."""
    name = safe_name(name)
    base = time.strftime("%Y-%m-%d_%H%M%S") + ("" if name == "video" else f"_{name}")
    run_dir, n = outputs_dir / base, 1
    while run_dir.exists():
        n += 1
        run_dir = outputs_dir / f"{base}_{n}"
    run_dir.mkdir(parents=True)
    shutil.copy2(video, run_dir / f"{name}.mp4")
    shutil.copy2(wav, run_dir / "audio.wav")
    shutil.copy2(image, run_dir / f"input{image.suffix.lower() or '.png'}")
    (run_dir / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return run_dir
