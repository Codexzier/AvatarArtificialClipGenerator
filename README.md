# Avatar Artificial Clip Generator

Lokaler Generator für sprechende Bilder (Talking Head mit Lippensynchronisation). Alles läuft lokal.
Ziel-Hardware: RTX 4070 Super (12 GB VRAM), 32 GB RAM, Pop!_OS.

**Stand: Etappe 2 (ComfyUI + Wan 2.2 S2V per Kommandozeile, ungetestet auf echter GPU).** Gradio-Oberfläche folgt.

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

## Video (Etappe 2)

```bash
scripts/install_comfyui.sh                 # ComfyUI + PyTorch (CUDA) in ComfyUI/.venv, ca. 3-4 GB
python scripts/download_models.py          # zeigt Modelle, Größe, Lizenz (ca. 23,6 GB gesamt)
python scripts/download_models.py --yes
scripts/start_comfyui.sh                   # in eigenem Terminal
python scripts/run_wan_s2v.py bild.png --text "Hallo!" --voice piper/de_DE-thorsten-high --quality preview
```

Stufen (`config.yaml`, `video.quality`): preview (2 s, 4 Schritte, Lightning-LoRA), fast, normal, high (20 Schritte ohne LoRA).
Das Ergebnis landet in `outputs/<Datum_Uhrzeit>/` (video.mp4, audio.wav, Eingabebild, settings.json).

Technik: Wan 2.2 S2V arbeitet mit 16 fps; ein Chunk liefert ca. 80 Frames (5 s), längere Clips werden über
`WanSoundImageToVideoExtend` verkettet (wie in der offiziellen ComfyUI-Vorlage). Standardmodell ist fp8_scaled
(15,3 GB); ComfyUI lagert auf 12 GB VRAM automatisch in den RAM aus. GGUF ist über `engines.wan_s2v.unet_loader: gguf`
und `WITH_GGUF=1 scripts/install_comfyui.sh` vorgesehen.

## Tests

```bash
python -m pytest
```

## Bekannte Grenzen
- Die Tests nutzen eine Mock-Stimme und ein simuliertes ComfyUI; echte Piper-Stimmen und der echte Wan-Lauf sind noch nicht getestet.
- Der Wert `trim_frames: 3` stammt aus der offiziellen Vorlage (Fix für das überbelichtete erste Bild); der Zusammenhang mit der Chunk-Zahl ist unklar und wird beim ersten echten Lauf geprüft.
- Die Schritte der Stufen normal/high sowie die Größe der Lightning-LoRA sind Schätzwerte.
