#!/usr/bin/env python3
"""Lädt deutsche Piper-Stimmen nach voices/piper/. Ohne --yes wird nur aufgelistet."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config, resolve_path

# Name -> ungefähre Größe in MB (Modell + Config)
VOICES = {
    "de_DE-thorsten-high": 110,
    "de_DE-thorsten_emotional-medium": 65,
    "de_DE-kerstin-low": 65,
    "de_DE-ramona-low": 65,
    "de_DE-eva_k-x_low": 20,
    "de_DE-karlsson-low": 65,
    "de_DE-pavoque-low": 65,
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("voices", nargs="*", help="Namen; leer = alle")
    p.add_argument("--yes", action="store_true", help="Download wirklich starten")
    a = p.parse_args()
    names = a.voices or list(VOICES)
    total = sum(VOICES.get(n, 70) for n in names)
    for n in names:
        print(f"  {n}  ca. {VOICES.get(n, 70)} MB")
    print(f"Gesamt ca. {total} MB")
    if not a.yes:
        print("Zum Herunterladen mit --yes erneut starten.")
        return
    target = resolve_path(load_config()["paths"]["voices_dir"]) / "piper"
    target.mkdir(parents=True, exist_ok=True)
    from piper.download_voices import download_voice

    for n in names:
        download_voice(n, target)
        print("fertig:", n)


if __name__ == "__main__":
    main()
