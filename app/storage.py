"""Schritt 6: Ergebnisordner outputs/<Datum_Uhrzeit>/ anlegen."""
import json
import shutil
import time
from pathlib import Path


def save_run(outputs_dir: Path, video: Path, wav: Path, image: Path, settings: dict) -> Path:
    base = time.strftime("%Y-%m-%d_%H%M%S")
    run_dir, n = outputs_dir / base, 1
    while run_dir.exists():
        n += 1
        run_dir = outputs_dir / f"{base}_{n}"
    run_dir.mkdir(parents=True)
    shutil.copy2(video, run_dir / "video.mp4")
    shutil.copy2(wav, run_dir / "audio.wav")
    shutil.copy2(image, run_dir / f"input{image.suffix.lower() or '.png'}")
    (run_dir / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return run_dir
