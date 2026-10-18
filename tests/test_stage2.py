import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.audio import write_wav
from app.comfy.client import ComfyClient, ComfyCancelled, ComfyError, ComfyOutOfMemory, output_files
from app.config import load_config
from app.engines.base import VideoSettings
from app.engines.wan_s2v import WanS2VEngine, build_workflow, chunks_needed
from app.storage import save_run
from app.video_post import mux_audio, video_duration

MODELS = load_config()["engines"]["wan_s2v"]


def check_refs(g):
    for nid, n in g.items():
        for k, v in n["inputs"].items():
            if isinstance(v, list):
                assert v[0] in g, f"{nid}.{k} -> fehlender Node {v[0]}"


@pytest.mark.parametrize("secs,expected", [(0.5, 1), (2, 1), (5, 1), (9.8, 2), (10, 2), (12, 3)])
def test_chunks_needed(secs, expected):
    assert chunks_needed(secs, 16) == expected


def test_chunks_exact_without_tolerance():
    assert chunks_needed(10, 16, 0) == 3


@pytest.mark.parametrize("chunks", [1, 2, 3])
def test_workflow_structure(chunks):
    s = VideoSettings(prompt="hallo", width=480, height=832, steps=6, cfg=1.0, seed=42)
    g, samplers = build_workflow(MODELS, s, "i.png", "a.wav", chunks, "avatargen/x/frame")
    check_refs(g)
    assert len(samplers) == chunks
    assert sum(n["class_type"] == "WanSoundImageToVideoExtend" for n in g.values()) == chunks - 1
    for sid in samplers:
        assert g[sid]["inputs"]["seed"] == 42 and g[sid]["inputs"]["steps"] == 6
    assert g["12"]["inputs"]["width"] == 480 and g["10"]["inputs"]["text"] == "hallo"
    assert g["44"]["inputs"]["filename_prefix"] == "avatargen/x/frame"
    # Kette: letzter Chunk speist Schnitt und Decoder
    assert g["40"]["inputs"]["samples"] == g["41"]["inputs"]["samples2"]
    json.dumps(g)


def test_workflow_no_lora_and_gguf():
    s = VideoSettings(prompt="x", use_lora=False)
    g, _ = build_workflow({**MODELS, "unet_loader": "gguf", "unet": "m.gguf"}, s, "i", "a", 1, "p")
    check_refs(g)
    assert "2" not in g and g["3"]["inputs"]["model"] == ["1", 0]
    assert g["1"]["class_type"] == "UnetLoaderGGUF" and g["1"]["inputs"] == {"unet_name": "m.gguf"}


class FakeWS:
    def __init__(self, messages):
        self.messages = [json.dumps(m) if isinstance(m, dict) else m for m in messages]
        self.closed = False

    def recv(self):
        return self.messages.pop(0)

    def close(self):
        self.closed = True


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body, self.text = status, body or {}, json.dumps(body or {})

    def json(self):
        return self._body


def make_client(monkeypatch, msgs):
    ws = FakeWS(msgs)
    c = ComfyClient(ws_factory=lambda url: ws)
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResp(200, {"prompt_id": "P"}))
    monkeypatch.setattr(c, "history", lambda pid: {"outputs": {"44": {"images": [{"filename": "f.png"}]}}})
    return c, ws


def ev(t, **d):
    return {"type": t, "data": d}


def test_run_progress(monkeypatch):
    c, ws = make_client(monkeypatch, [
        b"preview", ev("progress", value=1, max=4, node="13", prompt_id="P"),
        ev("progress", value=1, max=9, node="x", prompt_id="OTHER"),
        ev("executing", node=None, prompt_id="P")])
    seen = []
    h = c.run({}, lambda n, v, m: seen.append((n, v, m)))
    assert seen == [("13", 1, 4)] and ws.closed and output_files(h)[0]["filename"] == "f.png"


def test_run_errors(monkeypatch):
    c, _ = make_client(monkeypatch, [ev("execution_error", exception_type="torch.OutOfMemoryError",
                                        exception_message="CUDA out of memory", prompt_id="P")])
    with pytest.raises(ComfyOutOfMemory):
        c.run({})
    c, _ = make_client(monkeypatch, [ev("execution_interrupted", prompt_id="P")])
    with pytest.raises(ComfyCancelled):
        c.run({})
    c, _ = make_client(monkeypatch, [ev("execution_error", exception_type="ValueError",
                                        exception_message="kaputt", node_type="KSampler", node_id="13", prompt_id="P")])
    with pytest.raises(ComfyError, match="KSampler"):
        c.run({})
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResp(400, {"error": "bad"}))
    with pytest.raises(ComfyError, match="abgelehnt"):
        c.run({})


class FakeComfy:
    """Liefert statt echter Generierung ein paar Testbilder."""

    def __init__(self, frames_png):
        self.frames, self.freed, self.uploads = frames_png, False, []

    def is_up(self): return True
    def upload(self, path, name=None): self.uploads.append(name); return name
    def interrupt(self): pass
    def free(self): self.freed = True

    def run(self, graph, cb):
        for sid in ("13", "24"):
            if sid in graph:
                cb(sid, graph[sid]["inputs"]["steps"], graph[sid]["inputs"]["steps"])
        self.graph = graph
        return {"outputs": {"44": {"images": [{"filename": f"f{i}.png", "subfolder": "s", "type": "output"}
                                              for i in range(len(self.frames))]}}}

    def view(self, filename, subfolder="", type_="output"):
        return self.frames[int(filename[1:-4])]


def test_engine_end_to_end_with_fake_comfy(tmp_path):
    for i in range(8):  # 8 Testbilder
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x{i*30:02x}8040:s=64x48",
                        "-frames:v", "1", str(tmp_path / f"t{i}.png")], check=True)
    frames = [(tmp_path / f"t{i}.png").read_bytes() for i in range(8)]
    wav = tmp_path / "a.wav"
    write_wav(wav, (np.sin(np.arange(44100 * 1) * 0.05) * 8000).astype(np.int16), 22050)  # 2 s
    img = tmp_path / "bild.png"
    img.write_bytes(frames[0])
    fake = FakeComfy(frames)
    eng = WanS2VEngine(MODELS, fake)
    prog = []
    out = eng.generate(img, wav, VideoSettings(prompt="p", steps=4), tmp_path / "work", lambda f, t: prog.append((f, t)))
    assert fake.freed and prog[-1][0] == 1.0
    assert video_duration(out) == pytest.approx(2.0, abs=0.1)  # 8 Frames @16 fps, aufgefüllt auf Audiolänge
    final = mux_audio(out, wav, tmp_path / "final.mp4")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(final)],
                           capture_output=True, text=True).stdout.split()
    assert set(probe) == {"h264", "aac"}
    run = save_run(tmp_path / "outputs", final, wav, img, {"seed": 1})
    assert sorted(p.name for p in run.iterdir()) == ["audio.wav", "input.png", "settings.json", "video.mp4"]
