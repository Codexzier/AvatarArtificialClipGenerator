#!/usr/bin/env python3
"""Etappe 2: Bild + (WAV oder Text) -> Video per Kommandozeile. ComfyUI muss laufen."""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio import EFFECTS, trim_audio, wav_duration
from app.comfy.client import ComfyClient
from app.config import load_config, resolve_path
from app.engines.base import VideoSettings
from app.engines.wan_s2v import WanS2VEngine
from app.pipeline import AudioTooLongError, make_audio
from app.storage import save_run
from app.tts.base import TTSSettings
from app.tts.registry import available_engines, discover_voices
from app.video_post import mux_audio


def main():
    cfg = load_config()
    v = cfg["video"]
    p = argparse.ArgumentParser()
    p.add_argument("image", type=Path)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--wav", type=Path)
    src.add_argument("--text")
    p.add_argument("--voice", help="Stimmen-ID (mit --text)")
    p.add_argument("--speed", type=float, default=cfg["tts"]["speed"], help="Sprechtempo, >1 schneller (mit --text)")
    p.add_argument("--pause", type=float, default=cfg["tts"]["sentence_pause"], help="Satzpause in s (mit --text)")
    p.add_argument("--effect", choices=list(EFFECTS), default=cfg["tts"]["effect"], help="Audioeffekt (mit --text)")
    p.add_argument("--prompt", default="A person speaks calmly, natural lip movement and subtle head motion.")
    p.add_argument("--quality", choices=list(v["quality"]), default="preview")
    p.add_argument("--resolution", choices=list(v["resolutions"]), default="480p quer")
    p.add_argument("--seed", type=int)
    a = p.parse_args()

    work = resolve_path(cfg["paths"]["work_dir"])
    q = v["quality"][a.quality]
    limit = cfg["limits"]["max_audio_seconds"]
    preview_s = q.get("max_seconds")  # Vorschau: Audio wird gekürzt statt abgelehnt
    if a.text:
        engines = available_engines()
        flat = {x.id: x for vs in discover_voices(engines, resolve_path(cfg["paths"]["voices_dir"])).values() for x in vs}
        if a.voice not in flat:
            sys.exit("Mit --text wird --voice benötigt (siehe scripts/preview_audio.py --list).")
        try:
            wav = make_audio(a.text, engines[flat[a.voice].engine], flat[a.voice], TTSSettings(a.speed, a.pause),
                             a.effect, work, limit).path
        except AudioTooLongError as e:
            sys.exit(str(e))
    else:
        wav = a.wav
        if wav_duration(wav) > limit:
            sys.exit(f"Das Audio ist {wav_duration(wav):.1f} s lang, erlaubt sind {limit:g} s.")
    if preview_s and wav_duration(wav) > preview_s:
        print(f"Vorschau: Audio ({wav_duration(wav):.1f} s) wird auf {preview_s:g} s gekürzt.")
        wav = trim_audio(wav, work / "preview_trim.wav", preview_s)

    w, h = v["resolutions"][a.resolution]
    seed = a.seed if a.seed is not None else random.randint(0, 2**32 - 1)
    settings = VideoSettings(prompt=a.prompt, width=w, height=h, steps=q["steps"], cfg=q["cfg"],
                             use_lora=q["lora"], seed=seed, quality=a.quality)
    cc = cfg["comfyui"]
    engine = WanS2VEngine(cfg["engines"]["wan_s2v"], ComfyClient(cc["host"], cc["port"]),
                          resolve_path(cfg["paths"]["comfyui_dir"]), v["fps"], v["tail_tolerance_frames"], v["trim_frames"])

    def progress(frac, text):
        print(f"\r{frac * 100:5.1f} %  {text:<50}", end="", flush=True)

    try:
        silent = engine.generate(a.image, wav, settings, work, progress)
    except KeyboardInterrupt:
        engine.cancel()
        sys.exit("\nAbgebrochen.")
    print()
    final = mux_audio(silent, wav, work / (silent.stem.replace("_silent", "") + ".mp4"))
    run = save_run(resolve_path(cfg["paths"]["outputs_dir"]), final, wav, a.image,
                   {**vars(settings), "resolution": a.resolution, "engine": engine.name,
                    "audio_seconds": wav_duration(wav), "models": cfg["engines"]["wan_s2v"]})
    print("Fertig:", run / "video.mp4")


if __name__ == "__main__":
    main()
