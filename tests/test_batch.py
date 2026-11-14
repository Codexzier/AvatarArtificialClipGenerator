import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.batch import BatchRunner, parse_bulk, parse_rows
from app.comfy.client import ComfyCancelled
from app.engines.base import VideoEngine
from app.jobs import JobRequest, Pipeline
from app.storage import safe_name
from app.video_post import frames_to_video, video_duration
from app.audio import wav_duration, write_wav
from app.config import load_config
from app.tts.base import TTSEngine, Voice


class LogTTS(TTSEngine):
    name = "fake"
    log: list = []

    def list_voices(self, d): return []

    def synthesize(self, text, voice, settings, out_path):
        LogTTS.log.append(("tts", text))
        write_wav(out_path, np.zeros(int(22050 * len(text) / 10), dtype=np.int16), 22050)  # 10 Zeichen = 1 s
        return out_path


class LogVideo(VideoEngine):
    name = "wan_s2v"

    def __init__(self):
        self.calls, self.released, self.fail_on = [], 0, set()
        self.cancel_on = None

    def cancel(self): pass

    def release(self): self.released += 1

    def generate(self, image, wav, settings, work_dir, progress=None):
        LogTTS.log.append(("video", wav_duration(wav)))
        self.calls.append((settings.output_fps, self.keep_models, settings.seed))
        if len(self.calls) in self.fail_on:
            raise RuntimeError("Grafikspeicher voll")
        if len(self.calls) == self.cancel_on:
            raise ComfyCancelled("x")
        progress(0.5, "halb")
        out = work_dir / f"v{len(self.calls)}_silent.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=blue:s=64x64:d={wav_duration(wav)}",
                        "-pix_fmt", "yuv420p", str(out)], check=True)
        return out


@pytest.fixture
def setup(tmp_path):
    cfg = load_config()
    cfg["paths"] = {**cfg["paths"], "work_dir": str(tmp_path / "w"), "outputs_dir": str(tmp_path / "o")}
    eng = LogVideo()
    LogTTS.log = []
    p = Pipeline(cfg, {"fake": LogTTS()}, {"fake": [Voice("fake/v", "fake", "v")]}, {"wan_s2v": eng})
    img = tmp_path / "b.png"
    Image.new("RGB", (64, 64)).save(img)
    tpl = JobRequest(img, "", "fake/v", 1.0, 0.3, "none", "p", "quadratisch", "fast", 5, fps=24)
    return p, eng, tpl, tmp_path


def run(p, items, tpl, rnd=False):
    r = BatchRunner(p)
    r.start(items, tpl, rnd)
    r.join(60)
    return r


def test_audio_first_then_videos_and_keep_models(setup):
    p, eng, tpl, tmp = setup
    items = parse_rows([["eins", "a" * 20, ""], ["zwei", "b" * 30, ""], ["drei", "c" * 10, ""]])
    r = run(p, items, tpl)
    assert [k for k, _ in LogTTS.log] == ["tts"] * 3 + ["video"] * 3  # erst alle Sprachen
    assert [it.status for it in items] == ["fertig"] * 3
    assert [c[1] for c in eng.calls] == [True, True, False]  # Modelle bleiben bis zum letzten Video geladen
    assert eng.released == 1 and all(c[0] == 24 for c in eng.calls)
    assert sorted(p.name for p in (tmp / "o").iterdir() if p.name.endswith(("_eins", "_zwei", "_drei"))) and \
        any((d / "eins.mp4").exists() for d in (tmp / "o").iterdir())
    assert r.running is False


def test_failures_do_not_stop_the_list(setup):
    p, eng, tpl, _ = setup
    eng.fail_on = {1}
    items = parse_rows([["a", "x" * 10, ""], ["lang", "y" * 200, ""], ["c", "z" * 10, ""]])
    run(p, items, tpl)
    assert [it.status for it in items] == ["Fehler", "Fehler", "fertig"]
    assert "erlaubt" in items[1].detail and "Grafikspeicher" in items[0].detail
    assert len(eng.calls) == 2  # der zu lange Text erzeugt keinen Videojob


def test_cancel_marks_rest(setup):
    p, eng, tpl, _ = setup
    eng.cancel_on = 2
    items = parse_rows([["a", "x" * 10, ""], ["b", "y" * 10, ""], ["c", "z" * 10, ""]])
    run(p, items, tpl)
    assert [it.status for it in items] == ["fertig", "abgebrochen", "abgebrochen"]
    assert eng.released == 1


def test_random_vs_fixed_seed(setup):
    p, eng, tpl, _ = setup
    run(p, parse_rows([["a", "x" * 10, ""], ["b", "y" * 10, ""]]), tpl, rnd=False)
    assert [c[2] for c in eng.calls] == [5, 5]
    eng.calls.clear()
    run(p, parse_rows([["a", "x" * 10, ""], ["b", "y" * 10, ""]]), tpl, rnd=True)
    assert eng.calls[0][2] != 5 or eng.calls[1][2] != 5


def test_parse_rows_and_names():
    items = parse_rows([["Gruß/Welt.mp4", "Hallo", ""], ["", "  ", ""], ["Gruß/Welt", "Nochmal", ""], [None, "Ohne Name", ""]])
    assert [i.name for i in items] == ["Gruß_Welt", "Gruß_Welt_2", "clip_003"]
    assert safe_name("../../etc/passwd") == "etc_passwd" and safe_name("") == "video"
    assert parse_bulk("a | Hallo\n\nnur Text\nb|x | y") == [["a", "Hallo"], ["", "nur Text"], ["b", "x | y"]]


def test_frames_to_video_interpolates_and_keeps_length(tmp_path):
    for i in range(1, 17):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x{i * 10:02x}2040:s=64x64",
                        "-frames:v", "1", str(tmp_path / f"frame_{i:05d}.png")], check=True)
    for fps in (16, 24):
        out = frames_to_video(tmp_path, 16, 1.0, tmp_path / f"o{fps}.mp4", fps)
        assert video_duration(out) == pytest.approx(1.0, abs=0.08)
        n = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=r_frame_rate",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
        assert n == f"{fps}/1"
