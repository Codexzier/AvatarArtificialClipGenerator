#!/usr/bin/env python3
"""Probehören per Kommandozeile: Text -> WAV mit Längenangabe."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio import EFFECTS
from app.config import load_config, resolve_path
from app.pipeline import AudioTooLongError, make_audio
from app.tts.base import TTSSettings
from app.tts.registry import available_engines, discover_voices


def main():
    cfg = load_config()
    p = argparse.ArgumentParser()
    p.add_argument("text", nargs="?")
    p.add_argument("--voice", help="Stimmen-ID, z. B. piper/de_DE-thorsten-high")
    p.add_argument("--list", action="store_true", help="installierte Stimmen anzeigen")
    p.add_argument("--speed", type=float, default=cfg["tts"]["speed"])
    p.add_argument("--pause", type=float, default=cfg["tts"]["sentence_pause"])
    p.add_argument("--effect", choices=list(EFFECTS), default=cfg["tts"]["effect"])
    a = p.parse_args()

    engines = available_engines()
    voices = discover_voices(engines, resolve_path(cfg["paths"]["voices_dir"]))
    if a.list or not a.text:
        for eng, vs in voices.items():
            print(f"[{eng}]")
            for v in vs:
                print("  ", v.id)
        if not voices:
            print("Keine Stimmen gefunden. Zuerst scripts/download_piper_voices.py ausführen.")
        return
    flat = {v.id: v for vs in voices.values() for v in vs}
    if a.voice not in flat:
        sys.exit(f"Stimme '{a.voice}' nicht gefunden. Mit --list anzeigen.")
    voice = flat[a.voice]
    try:
        r = make_audio(a.text, engines[voice.engine], voice, TTSSettings(a.speed, a.pause), a.effect,
                       resolve_path(cfg["paths"]["work_dir"]), cfg["limits"]["max_audio_seconds"])
    except AudioTooLongError as e:
        sys.exit(str(e))
    print(f"{r.path}  ({r.duration:.1f} s)")


if __name__ == "__main__":
    main()
