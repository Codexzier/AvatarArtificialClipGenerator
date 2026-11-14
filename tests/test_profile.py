import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.audio import write_wav
from app.batch import BatchRunner, parse_rows
from app.config import load_config
from app.jobs import JobRequest, Pipeline
from app.profiles import clip_id, export_path, get_profile, profile_choices
from app.tts.base import Voice
from test_batch import LogTTS, LogVideo


def probe(path, entries, stream=None):
    cmd = ["ffprobe", "-v", "error"] + (["-select_streams", stream] if stream else []) + \
          ["-show_entries", entries, "-of", "default=nw=1", str(path)]
    return dict(line.split("=", 1) for line in subprocess.run(cmd, capture_output=True, text=True).stdout.split())


@pytest.fixture
def prof_setup(tmp_path):
    cfg = load_config()
    cfg["paths"] = {**cfg["paths"], "work_dir": str(tmp_path / "w"), "outputs_dir": str(tmp_path / "o")}
    cfg["profiles"]["mondschuerfer"]["export_dir"] = str(tmp_path / "clips")
    eng = LogVideo()
    LogTTS.log = []
    pl = Pipeline(cfg, {"fake": LogTTS()}, {"fake": [Voice("fake/v", "fake", "v")]}, {"wan_s2v": eng})
    img = tmp_path / "b.png"
    Image.new("RGB", (64, 64)).save(img)
    return pl, eng, img, tmp_path


def req(img, name, text="a" * 40, **kw):
    return JobRequest(img, text, "fake/v", 1.0, 0.3, "none", "p", "480p quer", "fast", 1, fps=16,
                      name=name, profile="mondschuerfer", **kw)


def test_choices_and_profile_values():
    cfg = load_config()
    assert [c[1] for c in profile_choices(cfg)] == ["individuell", "mondschuerfer"]
    assert profile_choices(cfg)[1][0] == "Avatar Mondschürfer"
    p = get_profile(cfg, "mondschuerfer")
    assert p["size"] == [480, 480] and p["fps"] == 30 and p["audio_rate"] == 32000 and p["audio_channels"] == 1
    assert get_profile(cfg, "individuell") is None


def test_clip_id():
    assert clip_id("clip_capsules_start.mp4") == "clip_capsules_start"
    assert clip_id("Größe & Mond/Schürfer") == "Groesse_Mond_Schuerfer"
    assert clip_id("  ") == "clip" and clip_id("../x") == "x"


def test_export_is_game_format(prof_setup):
    pl, eng, img, tmp = prof_setup
    run_dir, info = pl.run(req(img, "clip_capsules_start"))
    mpg = tmp / "clips" / "clip_capsules_start.mpg"
    assert mpg.exists() and info["export"] == str(mpg)
    assert (info["width"], info["height"], info["fps"]) == (480, 480, 30)  # Profil überschreibt 480p quer/16
    assert eng.calls[0][0] == 30
    fmt = probe(mpg, "format=format_name,duration")
    assert fmt["format_name"] == "mpeg" and float(fmt["duration"]) == pytest.approx(4.0, abs=0.15)
    v = probe(mpg, "stream=codec_name,width,height,avg_frame_rate", "v")
    assert v == {"codec_name": "mpeg1video", "width": "480", "height": "480", "avg_frame_rate": "30/1"}
    a = probe(mpg, "stream=codec_name,sample_rate,channels", "a")
    assert a == {"codec_name": "mp2", "sample_rate": "32000", "channels": "1"}
    assert (run_dir / "clip_capsules_start.mp4").exists()  # Archiv im Ergebnisordner


def test_no_silent_overwrite_and_missing_id(prof_setup):
    pl, eng, img, tmp = prof_setup
    pl.run(req(img, "clip_a"))
    n = len(eng.calls)
    with pytest.raises(FileExistsError, match="existiert bereits"):
        pl.run(req(img, "clip_a"))
    assert len(eng.calls) == n  # vor der Berechnung abgelehnt
    pl.run(req(img, "clip_a", overwrite=True))
    with pytest.raises(ValueError, match="Clip-ID"):
        pl.run(req(img, "   "))


def test_profile_limits_length(prof_setup):
    from app.pipeline import AudioTooLongError
    pl, eng, img, _ = prof_setup
    pl.cfg["profiles"]["mondschuerfer"]["max_seconds"] = 3
    with pytest.raises(AudioTooLongError, match="erlaubt sind 3"):
        pl.run(req(img, "lang", text="a" * 50))  # 5 s


def test_batch_with_profile_marks_existing(prof_setup):
    pl, eng, img, tmp = prof_setup
    (tmp / "clips").mkdir()
    (tmp / "clips" / "vorhanden.mpg").write_bytes(b"x")
    items = parse_rows([["vorhanden", "x" * 20, ""], ["Neu Clip", "y" * 20, ""]], clip_id)
    r = BatchRunner(pl)
    r.start(items, req(img, ""), False)
    r.join(60)
    assert [i.name for i in items] == ["vorhanden", "Neu_Clip"]
    assert items[0].status == "Fehler" and "existiert bereits" in items[0].detail
    assert items[1].status == "fertig" and (tmp / "clips" / "Neu_Clip.mpg").exists()
    assert (tmp / "clips" / "vorhanden.mpg").read_bytes() == b"x"
