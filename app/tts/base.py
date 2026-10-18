from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Voice:
    id: str        # eindeutig, z. B. "piper/de_DE-thorsten-high"
    engine: str    # z. B. "piper"
    label: str     # Anzeigename
    path: Path | None = None


@dataclass
class TTSSettings:
    speed: float = 1.0           # >1 schneller
    sentence_pause: float = 0.3  # Sekunden zwischen Sätzen


class TTSEngine(ABC):
    name: str

    @abstractmethod
    def list_voices(self, voices_dir: Path) -> list[Voice]:
        """Findet installierte Stimmen unter voices_dir/<engine>/."""

    @abstractmethod
    def synthesize(self, text: str, voice: Voice, settings: TTSSettings, out_path: Path) -> Path:
        """Erzeugt eine mono-WAV unter out_path und gibt den Pfad zurück."""
