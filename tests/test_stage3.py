import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.audio import wav_duration, write_wav
from app.config import load_config
from app.engines.base import VideoEngine
from app.history import list_runs
from app.jobs import JobRequest, Pipeline, suggest_resolution
from app.sysinfo import memory_hint
from app.tts.base import TTSEngine, Voice
from app.ui import build_ui, char_info


class FakeTTS(TTSEngine):
    name = "fake"

    def list_voices(self, d): return []

    def synthesize(self, text, voice, settings, out_path):
        write_wav(out_path, np.zeros(int(22050 * len(text) / 10), dtype=np.int16), 22050)  # 10 Zeichen = 1 s
        return out_path


class FakeVideo(VideoEngine):
    name = "wan_s2v"

    def __init__(self): self.seen, self.cancelled = None, False

    def cancel(self): self.cancelled = True

    def generate(self, image, wav, settings, work_dir, progress=None):
        self.seen = (settings, wav_duration(wav))
        progress(0.5, "halb")
        out = work_dir / "x_silent.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=%f" % wav_duration(wav),
                        "-pix_fmt", "yuv420p", str(out)], check=True)
        return out


@pytest.fixture
def pipe(tmp_path):
    cfg = load_config()
    cfg["paths"] = {**cfg["paths"], "work_dir": str(tmp_path / "work"), "outputs_dir": str(tmp_path / "out")}
    voice = Voice("fake/v", "fake", "v")
    eng = FakeVideo()
    return Pipeline(cfg, {"fake": FakeTTS()}, {"fake": [voice]}, {"wan_s2v": eng}), eng


def req(tmp_path, text="a" * 30, quality="fast", seed=None):
    img = tmp_path / "bild.png"
    Image.new("RGB", (200, 100)).save(img)
    return JobRequest(img, text, "fake/v", 1.0, 0.3, "none", "prompt", "quadratisch", quality, seed)


def test_run_saves_everything(pipe, tmp_path):
    p, eng = pipe
    prog = []
    run_dir, info = p.run(req(tmp_path, seed=7), lambda f, t: prog.append(f))
    assert prog[0] == 0.0 and prog[-1] == 1.0
    assert eng.seen[0].seed == 7 and (eng.seen[0].width, eng.seen[0].height) == (480, 480)
    saved = json.loads((run_dir / "settings.json").read_text())
    assert saved["text"] == "a" * 30 and saved["seed"] == 7 and saved["voice"] == "fake/v"
    assert wav_duration(run_dir / "audio.wav") == pytest.approx(3.0, abs=0.1)
    assert list_runs(tmp_path / "out")[0]["settings"]["quality"] == "fast"


def test_preview_trims_audio(pipe, tmp_path):
    p, eng = pipe
    p.run(req(tmp_path, quality="preview"), None)
    assert eng.seen[1] == pytest.approx(2.0, abs=0.1)
    assert eng.seen[0].steps == 4 and eng.seen[0].use_lora


def test_too_long_audio_rejected(pipe, tmp_path):
    from app.pipeline import AudioTooLongError
    p, eng = pipe
    with pytest.raises(AudioTooLongError):
        p.run(req(tmp_path, text="a" * 150), None)
    assert eng.seen is None  # kein Videojob


def test_cancel_forwarded(pipe):
    p, eng = pipe
    p._active = eng
    p.cancel()
    assert eng.cancelled


def test_suggest_resolution(tmp_path):
    r = load_config()["video"]["resolutions"]
    for size, exp in [((200, 100), "480p quer"), ((100, 200), "480p hoch"), ((100, 100), "quadratisch")]:
        f = tmp_path / "i.png"
        Image.new("RGB", size).save(f)
        assert suggest_resolution(f, r) == exp


def test_memory_hint(tmp_path):
    f = tmp_path / "mi"
    f.write_text("MemTotal: 16000000 kB\nSwapTotal: 1000000 kB\n")
    assert "Swap" in memory_hint(str(f))
    f.write_text("MemTotal: 32000000 kB\nSwapTotal: 20000000 kB\n")
    assert memory_hint(str(f)) is None
    assert memory_hint(str(tmp_path / "nope")) is None


def test_char_info_and_ui_builds(pipe):
    p, _ = pipe
    assert "140" in char_info("", p.cfg)
    assert build_ui(p) is not None
