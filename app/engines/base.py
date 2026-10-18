from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# progress(anteil 0..1, text)
ProgressFn = Callable[[float, str], None]


@dataclass
class VideoSettings:
    prompt: str
    width: int = 832
    height: int = 480
    steps: int = 4
    cfg: float = 1.0
    use_lora: bool = True
    seed: int = 0
    quality: str = "fast"
    negative_prompt: str = ""
    extra: dict = field(default_factory=dict)


class VideoEngine(ABC):
    name: str

    @abstractmethod
    def generate(self, image: Path, wav: Path, settings: VideoSettings, work_dir: Path,
                 progress: ProgressFn | None = None) -> Path:
        """Erzeugt ein Video ohne Ton (H.264) exakt in der Länge der WAV und gibt den Pfad zurück."""

    @abstractmethod
    def cancel(self) -> None:
        """Bricht den laufenden Job ab."""
