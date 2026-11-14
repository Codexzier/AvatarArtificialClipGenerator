# Avatar Artificial Clip Generator

Lokaler Generator für sprechende Bilder (Talking Head mit Lippensynchronisation). Alles läuft lokal.
Ziel-Hardware: RTX 4070 Super (12 GB VRAM), 32 GB RAM, Pop!_OS.

**Stand: Etappe 3 (Gradio-Oberfläche).** Wan 2.2 S2V wurde auf einer RTX 4070 SUPER getestet (Vorschau, 5 s und 8 s Clips); die Oberfläche selbst ist bisher nur mit Mock-Engines getestet.

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

## Bedienung (Oberfläche)

```bash
scripts/start.sh        # startet ComfyUI (falls nicht schon aktiv) und die App auf http://127.0.0.1:7860
```

- Die Oberfläche ist kompakt für ein Fenster von ca. 600x400 Pixeln gebaut: Tabs „Erstellen / Ergebnis / Verlauf", seltene Einstellungen im Klappmenü „Mehr"; nach dem Erzeugen springt die App zum Ergebnis.
- **Erstellen:** Bild hochladen (die Auflösung wird nach dem Seitenverhältnis vorgeschlagen), Text eingeben, Bewegungs-Vorlage
  oder eigenen Prompt, Stimme/Tempo/Pause/Effekt wählen, mit „Probehören" Stimme und Länge prüfen, dann „Video erzeugen".
- Die Qualitätsstufe steuert Schritte und Lightning-LoRA; „Vorschau" kürzt das Audio auf 2 s.
- Es läuft immer nur ein Job; weitere warten in der Warteschlange. „Abbrechen" stoppt den laufenden Job.
- **Liste:** mehrere Clips am Stück. Pro Zeile Zieldateiname und Text (oder viele Zeilen auf einmal im Format `name | text`
  einfügen). Es gelten die Einstellungen aus „Erstellen“ (Bild, Stimme, Auflösung, Stufe, Bildrate). Ablauf: zuerst wird
  die Sprache aller Texte vorbereitet (CPU), dann Video für Video erzeugt; die Modelle bleiben dabei geladen und werden erst
  nach der ganzen Liste freigegeben. Ein Fehler (z. B. Text zu lang, Speicher voll) stoppt die Liste nicht. Ergebnis:
  `outputs/<Datum_Uhrzeit>_<name>/<name>.mp4`.
- **Bildrate:** 16 fps ist nativ (Standard). 24 fps wird per ffmpeg aus den 16 fps berechnet (CPU, nach dem Modell; Länge und
  Lippensync bleiben gleich; bei schnellen Mundbewegungen können leichte Schlieren entstehen). Gemessen auf einer langsamen
  4-Kern-Testmaschine: ca. 28 s für 10 s Video in 480p, ca. 70 s in 720p.
- **Profil (Combobox ganz oben):** „Individuell“ lässt alle Einstellungen frei. „Avatar Mondschürfer“ erzeugt das
  Spielformat (pl_mpeg): `.mpg` (MPEG-1 Programmstream), 480×480, 30 fps, MP2 32 kHz mono, höchstens 10 s. Das Profil
  sperrt Auflösung und Bildrate, verlangt eine Clip-ID (= Dateiname, z. B. `clip_capsules_start`, nur a-z, 0-9, `_`, `-`) und
  legt die `.mpg` im Zielordner ab (`profiles.mondschuerfer.export_dir` in `config.yaml`, in der App im Klappmenü
  änderbar; später auf `assets/clips/` des Spiels stellen). Vorhandene Clips werden nur mit der Option „Vorhandene Clips
  überschreiben“ ersetzt. In der Liste ist die Spalte „Dateiname“ die Clip-ID. Zusätzlich bleibt im Ergebnisordner
  (`outputs/…`) die MP4-Fassung zur Ansicht. Die Qualität (`video_qscale: 3`) und die Audiobitrate (96 kbit/s) sind
  Startwerte, weil die Bitrate im Spiel nicht festgelegt war.
- **Verlauf:** bisherige Clips mit ihren Einstellungen (`outputs/<Datum_Uhrzeit>/`).
- Fehlt Auslagerungsspeicher (Swap < 8 GB bei < 48 GB RAM), zeigt die App einen Hinweis.

## Desktop-Anwendung (Linux, Pop!_OS)

Statt im Browser läuft die App in einem eigenen Fenster (ca. 620x470) mit Eintrag im Anwendungsmenü.
Ein Klick startet ComfyUI und die Oberfläche, das Schließen des Fensters beendet beides (und gibt den VRAM frei).

```bash
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 \
     gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav
scripts/install_launcher.sh        # pywebview in der venv + Menü-Eintrag mit Icon
scripts/avatargen.sh               # oder direkt starten; --stop beendet eine laufende Instanz
```

Fenster-Rückfall: Ist GTK/WebKit nicht nutzbar, nutzt die App Chromium oder Google Chrome im App-Modus (ohne
Adressleiste). Firefox hat keinen solchen Modus; ohne pywebview und Chromium/Chrome startet die Desktop-Variante nicht
(dann weiter `scripts/start.sh` und den Browser benutzen). Bekannte Grenze: Das Videoabspielen im WebKit-Fenster braucht die
GStreamer-Pakete oben; sonst Chromium/Chrome installieren.

## Tests

```bash
python -m pytest
```

## Bekannte Grenzen
- Die Tests nutzen eine Mock-Stimme und ein simuliertes ComfyUI; echte Piper-Stimmen und der echte Wan-Lauf sind noch nicht getestet.
- Der Wert `trim_frames: 3` stammt aus der offiziellen Vorlage (Fix für das überbelichtete erste Bild); der Zusammenhang mit der Chunk-Zahl ist unklar und wird beim ersten echten Lauf geprüft.
- Die Schritte der Stufen normal/high sowie die Größe der Lightning-LoRA sind Schätzwerte.
