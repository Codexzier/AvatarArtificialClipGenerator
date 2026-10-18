"""WAV-Hilfen und ffmpeg-Audioeffekte."""
import subprocess
import wave
from pathlib import Path

import numpy as np

EFFECTS = {
    "none": None,
    "robot": "afftfilt=real='hypot(re,im)*cos(0)':imag='hypot(re,im)*sin(0)':win_size=512:overlap=0.75",
    "radio": "highpass=f=500,lowpass=f=3000,acompressor=threshold=0.1:ratio=6,volume=1.5",
    "reverb": "aecho=0.8:0.88:60|120:0.4|0.3",
}
EFFECT_LABELS = {"none": "keiner", "robot": "Roboter", "radio": "Funkgerät", "reverb": "Hall"}


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    """Schreibt mono int16."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.astype("<i2").tobytes())


def silence(rate: int, seconds: float) -> np.ndarray:
    return np.zeros(int(rate * max(seconds, 0.0)), dtype=np.int16)


def _ffmpeg(args: list[str]) -> None:
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg fehlgeschlagen: {r.stderr.strip()}")


def apply_effect(src: Path, dst: Path, effect: str) -> Path:
    """Wendet einen Effekt an (Schlüssel aus EFFECTS). 'none' kopiert nur."""
    if effect not in EFFECTS:
        raise ValueError(f"Unbekannter Effekt: {effect}")
    flt = EFFECTS[effect]
    args = ["-i", str(src)]
    if flt:
        args += ["-af", flt]
    _ffmpeg([*args, "-c:a", "pcm_s16le", str(dst)])
    return dst


def convert_for_engine(src: Path, dst: Path, rate: int = 16000, channels: int = 1) -> Path:
    """Passt Abtastrate und Kanalzahl an die Video-Engine an."""
    _ffmpeg(["-i", str(src), "-ar", str(rate), "-ac", str(channels), "-c:a", "pcm_s16le", str(dst)])
    return dst


def trim_audio(src: Path, dst: Path, seconds: float) -> Path:
    """Schneidet das Audio hart auf `seconds` (kurzes Ausblenden gegen Knacken)."""
    fade = min(0.05, seconds / 4)
    _ffmpeg(["-i", str(src), "-t", f"{seconds:.3f}", "-af", f"afade=t=out:st={seconds - fade:.3f}:d={fade:.3f}",
             "-c:a", "pcm_s16le", str(dst)])
    return dst
