from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.audio import EFFECTS, apply_effect, convert_for_engine, wav_duration, write_wav
from app.pipeline import AudioTooLongError, make_audio
from app.tts.base import TTSSettings, Voice
from app.tts.piper_engine import PiperEngine, split_sentences
from app.tts.registry import discover_voices


def tone(path: Path, seconds: float, rate=22050):
    t = np.arange(int(rate * seconds)) / rate
    write_wav(path, (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16), rate)
    return path


def test_split_sentences():
    assert split_sentences("Hallo Welt. Wie geht's? Gut!") == ["Hallo Welt.", "Wie geht's?", "Gut!"]
    assert split_sentences("  ") == []


@pytest.mark.parametrize("effect", list(EFFECTS))
def test_effects_run(tmp_path, effect):
    src = tone(tmp_path / "a.wav", 1.0)
    out = apply_effect(src, tmp_path / f"{effect}.wav", effect)
    # Hall hängt eine kurze Ausklingzeit an
    assert 1.0 - 0.1 <= wav_duration(out) <= 1.3


def test_convert_for_engine(tmp_path):
    out = convert_for_engine(tone(tmp_path / "a.wav", 1.0), tmp_path / "b.wav", 16000, 1)
    import wave
    with wave.open(str(out)) as w:
        assert (w.getframerate(), w.getnchannels()) == (16000, 1)


def test_discover_voices(tmp_path):
    d = tmp_path / "piper"
    d.mkdir()
    (d / "ok.onnx").write_bytes(b"x")
    (d / "ok.onnx.json").write_text("{}")
    (d / "kaputt.onnx").write_bytes(b"x")  # ohne Config -> ignoriert
    voices = discover_voices({"piper": PiperEngine()}, tmp_path)
    assert [v.id for v in voices["piper"]] == ["piper/ok"]
    assert discover_voices({"piper": PiperEngine()}, tmp_path / "leer") == {}


class FakeVoice:
    config = SimpleNamespace(sample_rate=22050)

    def synthesize(self, text, syn_config=None):
        n = int(22050 * 0.5 * syn_config.length_scale)
        yield SimpleNamespace(audio_int16_array=np.ones(n, dtype=np.int16))


def test_piper_pauses_and_speed(tmp_path, monkeypatch):
    pytest.importorskip("piper")
    eng = PiperEngine()
    monkeypatch.setattr(eng, "_load", lambda v: FakeVoice())
    v = Voice("piper/x", "piper", "x", Path("x.onnx"))
    out = eng.synthesize("Eins. Zwei.", v, TTSSettings(1.0, 0.4), tmp_path / "o.wav")
    assert wav_duration(out) == pytest.approx(0.5 + 0.4 + 0.5, abs=0.01)
    out = eng.synthesize("Eins. Zwei.", v, TTSSettings(2.0, 0.0), tmp_path / "o2.wav")
    assert wav_duration(out) == pytest.approx(0.5, abs=0.01)


def test_make_audio_limit(tmp_path, monkeypatch):
    pytest.importorskip("piper")
    eng = PiperEngine()
    monkeypatch.setattr(eng, "_load", lambda v: FakeVoice())
    v = Voice("piper/x", "piper", "x", Path("x.onnx"))
    r = make_audio("Eins.", eng, v, TTSSettings(), "none", tmp_path, 10)
    assert r.duration == pytest.approx(0.5, abs=0.05)
    with pytest.raises(AudioTooLongError, match="erlaubt sind 1 s"):
        make_audio("Eins. Zwei. Drei.", eng, v, TTSSettings(), "none", tmp_path, 1)
