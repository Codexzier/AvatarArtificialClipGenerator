"""Pipeline für die Oberfläche: Text -> Audio -> Video -> Muxen -> Speichern."""
import random
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from app.audio import trim_audio, wav_duration
from app.config import resolve_path
from app.engines.base import VideoEngine, VideoSettings
from app.pipeline import AudioResult, make_audio
from app.storage import save_run
from app.tts.base import TTSEngine, TTSSettings, Voice
from app.video_post import mux_audio


@dataclass
class JobRequest:
    image: Path
    text: str
    voice_id: str
    speed: float
    pause: float
    effect: str
    prompt: str
    resolution: str
    quality: str
    seed: int | None = None
    engine: str = "wan_s2v"


def suggest_resolution(image: Path, resolutions: dict) -> str:
    """Schlägt anhand des Bildseitenverhältnisses eine 480p-Auflösung vor."""
    with Image.open(image) as im:
        ratio = im.width / im.height
    name = "480p quer" if ratio > 1.2 else "480p hoch" if ratio < 0.83 else "quadratisch"
    return name if name in resolutions else next(iter(resolutions))


class Pipeline:
    def __init__(self, cfg: dict, tts_engines: dict[str, TTSEngine], voices: dict[str, list[Voice]],
                 video_engines: dict[str, VideoEngine]):
        self.cfg, self.tts, self.video_engines = cfg, tts_engines, video_engines
        self.voices = {v.id: v for vs in voices.values() for v in vs}
        self.work = resolve_path(cfg["paths"]["work_dir"])
        self.outputs = resolve_path(cfg["paths"]["outputs_dir"])
        self._active: VideoEngine | None = None
        self._lock = threading.Lock()  # immer nur ein Videojob

    def _voice(self, voice_id: str) -> Voice:
        if voice_id not in self.voices:
            raise ValueError("Bitte eine Stimme auswählen (keine installiert? scripts/download_piper_voices.py).")
        return self.voices[voice_id]

    def preview_audio(self, text: str, voice_id: str, speed: float, pause: float, effect: str) -> AudioResult:
        v = self._voice(voice_id)
        return make_audio(text, self.tts[v.engine], v, TTSSettings(speed, pause), effect, self.work,
                          self.cfg["limits"]["max_audio_seconds"])

    def cancel(self) -> None:
        if self._active:
            self._active.cancel()

    def run(self, req: JobRequest, progress=None) -> tuple[Path, dict]:
        """Gibt (Ergebnisordner, settings) zurück. Fehler als Exceptions mit verständlicher Meldung."""
        report = progress or (lambda f, t: None)
        v = self.cfg["video"]
        q = v["quality"][req.quality]
        with self._lock:
            report(0.0, "Erzeuge Audio")
            audio = self.preview_audio(req.text, req.voice_id, req.speed, req.pause, req.effect)
            wav = audio.path
            if q.get("max_seconds") and audio.duration > q["max_seconds"]:
                wav = trim_audio(wav, self.work / "preview_trim.wav", q["max_seconds"])
            w, h = v["resolutions"][req.resolution]
            seed = req.seed if req.seed is not None else random.randint(0, 2**32 - 1)
            settings = VideoSettings(prompt=req.prompt, width=w, height=h, steps=q["steps"], cfg=q["cfg"],
                                     use_lora=q["lora"], seed=seed, quality=req.quality)
            engine = self.video_engines[req.engine]
            self._active = engine
            try:
                silent = engine.generate(req.image, wav, settings, self.work,
                                         lambda f, t: report(0.05 + 0.93 * f, t))
            finally:
                self._active = None
            report(0.98, "Füge Ton hinzu")
            final = mux_audio(silent, wav, self.work / silent.name.replace("_silent", ""))
            info = {**asdict(req), "image": req.image.name, "motion_prompt": req.prompt, "seed": seed, "steps": q["steps"], "cfg": q["cfg"],
                    "lora": q["lora"], "width": w, "height": h, "audio_seconds": round(wav_duration(wav), 2),
                    "voice": req.voice_id, "models": self.cfg["engines"].get(req.engine, {})}
            run_dir = save_run(self.outputs, final, wav, req.image, info)
            report(1.0, "Fertig")
            return run_dir, info
