"""Schritte 1-3 der Pipeline: Text -> TTS -> Längenprüfung -> Effekt."""
import time
from dataclasses import dataclass
from pathlib import Path

from app.audio import EFFECTS, apply_effect, wav_duration
from app.tts.base import TTSEngine, TTSSettings, Voice


class AudioTooLongError(Exception):
    pass


@dataclass
class AudioResult:
    path: Path
    duration: float


def estimate_seconds(text: str, chars_per_second: float) -> float:
    return len(text) / chars_per_second


def make_audio(text: str, engine: TTSEngine, voice: Voice, settings: TTSSettings,
               effect: str, work_dir: Path, max_seconds: float) -> AudioResult:
    """Erzeugt das WAV. Über max_seconds -> AudioTooLongError (kein Videojob)."""
    if effect not in EFFECTS:
        raise ValueError(f"Unbekannter Effekt: {effect}")
    work_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    raw = engine.synthesize(text, voice, settings, work_dir / f"tts_{stamp}.wav")
    path = apply_effect(raw, work_dir / f"audio_{stamp}.wav", effect)
    duration = wav_duration(path)
    if duration > max_seconds:
        raise AudioTooLongError(
            f"Das Audio ist {duration:.1f} s lang, erlaubt sind {max_seconds:g} s. "
            "Bitte den Text kürzen oder das Sprechtempo erhöhen."
        )
    return AudioResult(path, duration)
