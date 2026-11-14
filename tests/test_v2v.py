import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.config import load_config
from app.engines.wan_fun_control import V2VSettings, WanFunControlEngine, build_v2v_workflow
from app.v2v import V2VPipeline, V2VRequest, build_prompt
from app.video_post import has_audio, prepare_control_clip, probe_frames, video_duration
from test_stage2 import check_refs

CFG = load_config()
MODELS = CFG["engines_v2v"]["wan_fun_control_5b"]


def make_clip(path: Path, seconds: float, fps: int = 30, size="640x360", audio=True):
    args = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s={size}:r={fps}:d={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}", "-c:a", "aac"]
    subprocess.run(args + ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-shortest", str(path)], check=True)
    return path


def test_workflow_canny_with_ref():
    s = V2VSettings(prompt="p", width=960, height=544, length=121, steps=12, seed=3)
    g = build_v2v_workflow(MODELS, s, "c.mp4", "r.png", "x/frame")
    check_refs(g)
    assert g["11"]["inputs"]["control_video"] == ["9", 0] and g["11"]["inputs"]["ref_image"] == ["10", 0]
    assert (g["11"]["inputs"]["width"], g["11"]["inputs"]["height"], g["11"]["inputs"]["length"]) == (960, 544, 121)
    assert g["12"]["inputs"]["steps"] == 12 and g["12"]["inputs"]["seed"] == 3
    assert g["1"]["inputs"]["unet_name"] == "wan2.2_fun_control_5B_bf16.safetensors"
    json.dumps(g)


def test_workflow_direct_without_ref():
    g = build_v2v_workflow(MODELS, V2VSettings(prompt="p", control="direct"), "c.mp4", None, "x/frame")
    check_refs(g)
    assert "9" not in g and "10" not in g and "ref_image" not in g["11"]["inputs"]
    assert g["11"]["inputs"]["control_video"] == ["8", 0]
    with pytest.raises(ValueError):
        build_v2v_workflow(MODELS, V2VSettings(prompt="p", control="tiefe"), "c", None, "x")


def test_resolutions_are_multiples_of_32():
    for w, h in CFG["v2v"]["resolutions"].values():
        assert w % 32 == 0 and h % 32 == 0


def test_prepare_trims_to_5s_at_24fps(tmp_path):
    src = make_clip(tmp_path / "in.mp4", 7, fps=30)
    n = prepare_control_clip(src, tmp_path / "c.mp4", 832, 480, 24, 121)
    assert n == 121 and probe_frames(tmp_path / "c.mp4") == 121
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", str(tmp_path / "c.mp4")], capture_output=True, text=True).stdout.strip()
    assert info == "832,480"


def test_prepare_short_clip_rounds_to_4k_plus_1(tmp_path):
    src = make_clip(tmp_path / "in.mp4", 2, fps=24, audio=False)
    assert prepare_control_clip(src, tmp_path / "c.mp4", 832, 480, 24, 121) == 45  # 48 Bilder -> 45
    assert not has_audio(src)


def test_build_prompt_styles():
    pos, neg = build_prompt(CFG, "A rover drives over regolith.", "fotorealistisch")
    assert pos.startswith("A rover drives over regolith, photorealistic") and "video game" in neg
    assert build_prompt(CFG, "x", "keiner") == ("x", "")


class FakeComfy:
    def __init__(self, png):
        self.png, self.uploads, self.freed = png, [], False

    def is_up(self): return True
    def upload(self, path, name=None): self.uploads.append(name); return name
    def interrupt(self): pass
    def free(self): self.freed = True

    def run(self, graph, cb):
        self.graph = graph
        cb("12", 5, 10)
        n = graph["11"]["inputs"]["length"]
        return {"outputs": {"14": {"images": [{"filename": f"f{i}.png"} for i in range(n)]}}}

    def view(self, filename, subfolder="", type_="output"):
        return self.png


def test_pipeline_end_to_end(tmp_path):
    cfg = load_config()
    cfg["paths"] = {**cfg["paths"], "work_dir": str(tmp_path / "w"), "outputs_dir": str(tmp_path / "o")}
    png = tmp_path / "f.png"
    Image.new("RGB", (832, 480), (40, 90, 160)).save(png)
    fake = FakeComfy(png.read_bytes())
    pipe = V2VPipeline(cfg, WanFunControlEngine(MODELS, fake))
    ref = tmp_path / "ref.png"
    Image.new("RGB", (100, 100)).save(ref)
    prog = []
    run_dir, info = pipe.run(V2VRequest(make_clip(tmp_path / "in.mp4", 6), "A rover", "comic", "canny",
                                        "480p 16:9 (832x480)", "preview", 9, ref, True, "mond rover"),
                             lambda f, t: prog.append(f))
    assert fake.freed and prog[-1] == 1.0
    assert fake.graph["12"]["inputs"]["steps"] == 10 and "comic book" in fake.graph["5"]["inputs"]["text"]
    assert info["frames"] == 121 and info["seconds"] == pytest.approx(5.04, abs=0.01)
    out = run_dir / "mond rover.mp4"
    assert video_duration(out) == pytest.approx(5.04, abs=0.1)
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,avg_frame_rate",
                              "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.split()
    assert "h264,24/1" in streams and any(s.startswith("aac") for s in streams)
    assert sorted(p.name for p in run_dir.iterdir()) == ["audio.wav", "input.mp4", "mond rover.mp4", "referenz.png", "settings.json"]


def test_pipeline_requires_prompt(tmp_path):
    cfg = load_config()
    pipe = V2VPipeline(cfg, WanFunControlEngine(MODELS, FakeComfy(b"")))
    with pytest.raises(ValueError, match="beschreiben"):
        pipe.run(V2VRequest(tmp_path / "x.mp4", "  ", "comic", "canny", "480p 16:9 (832x480)", "preview"))
