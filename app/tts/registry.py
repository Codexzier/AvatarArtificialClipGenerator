from pathlib import Path

from app.tts.base import TTSEngine, Voice
from app.tts.piper_engine import PiperEngine


def available_engines() -> dict[str, TTSEngine]:
    return {e.name: e for e in (PiperEngine(),)}


def discover_voices(engines: dict[str, TTSEngine], voices_dir: Path) -> dict[str, list[Voice]]:
    """Stimmen nach Engine gruppiert; Engines ohne Stimmen entfallen."""
    found = {name: e.list_voices(voices_dir) for name, e in engines.items()}
    return {name: v for name, v in found.items() if v}
