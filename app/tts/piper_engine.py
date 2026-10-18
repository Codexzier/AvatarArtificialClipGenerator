import re
from pathlib import Path

import numpy as np

from app.audio import silence, write_wav
from app.tts.base import TTSEngine, TTSSettings, Voice

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


class PiperEngine(TTSEngine):
    """Piper auf der CPU, kein VRAM."""

    name = "piper"

    def __init__(self):
        self._loaded = {}

    def list_voices(self, voices_dir: Path) -> list[Voice]:
        folder = voices_dir / self.name
        if not folder.is_dir():
            return []
        return [
            Voice(id=f"{self.name}/{m.stem}", engine=self.name, label=m.stem, path=m)
            for m in sorted(folder.glob("*.onnx"))
            if m.with_name(m.name + ".json").exists()
        ]

    def _load(self, voice: Voice):
        if voice.path not in self._loaded:
            from piper import PiperVoice  # erst hier, damit Tests ohne Piper laufen

            self._loaded[voice.path] = PiperVoice.load(voice.path, use_cuda=False)
        return self._loaded[voice.path]

    def synthesize(self, text: str, voice: Voice, settings: TTSSettings, out_path: Path) -> Path:
        from piper import SynthesisConfig

        sentences = split_sentences(text)
        if not sentences:
            raise ValueError("Der Text ist leer.")
        pv = self._load(voice)
        cfg = SynthesisConfig(length_scale=1.0 / max(settings.speed, 0.1))
        rate = pv.config.sample_rate
        parts = []
        for i, sentence in enumerate(sentences):
            for chunk in pv.synthesize(sentence, syn_config=cfg):
                parts.append(chunk.audio_int16_array)
            if i < len(sentences) - 1:
                parts.append(silence(rate, settings.sentence_pause))
        write_wav(out_path, np.concatenate(parts), rate)
        return out_path
