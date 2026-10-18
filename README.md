# Avatar Artificial Clip Generator

Lokaler Generator für sprechende Bilder (Talking Head mit Lippensynchronisation). Alles läuft lokal.
Ziel-Hardware: RTX 4070 Super (12 GB VRAM), 32 GB RAM, Pop!_OS.

**Stand: Etappe 1 (TTS + Probehören).** Video-Engine (ComfyUI, Wan 2.2 S2V) und Gradio-Oberfläche folgen.

## Installation (Etappe 1)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt install ffmpeg
```

## Stimmen

```bash
python scripts/download_piper_voices.py          # zeigt Liste und Größe (ca. 455 MB gesamt)
python scripts/download_piper_voices.py --yes    # lädt alle nach voices/piper/
python scripts/download_piper_voices.py de_DE-thorsten-high --yes   # nur eine
```

Stimmen liegen unter `voices/<engine>/` und werden automatisch erkannt (Piper-Lizenzen je Stimme prüfen).

## Probehören

```bash
python scripts/preview_audio.py --list
python scripts/preview_audio.py "Hallo, ich bin dein Avatar." --voice piper/de_DE-thorsten-high \
    --speed 1.0 --pause 0.3 --effect robot
```

Effekte: `none`, `robot`, `radio`, `reverb`. Audio über 10 s wird abgelehnt (`config.yaml`).

## Tests

```bash
python -m pytest
```

## Bekannte Grenzen
- Die Tests nutzen eine Mock-Stimme; echte Piper-Stimmen sind noch nicht in dieser Umgebung getestet.
