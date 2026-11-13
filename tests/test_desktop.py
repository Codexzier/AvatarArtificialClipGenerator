import os
import subprocess
from pathlib import Path

from app import desktop
from app.launcher import desktop_entry, install


def test_find_browser_order():
    found = {"google-chrome": "/usr/bin/google-chrome", "chromium": None}
    assert desktop.find_browser(lambda n: found.get(n)) == "/usr/bin/google-chrome"
    assert desktop.find_browser(lambda n: None) is None


def test_desktop_entry_quotes_paths_with_spaces(tmp_path):
    p = tmp_path / "Artificial Intelligence" / "Projekt $x"
    (p / "scripts").mkdir(parents=True)
    text = desktop_entry(p)
    assert f'Exec="{p}/scripts/avatargen.sh"'.replace("$", "\\$") in text
    assert "Terminal=false" in text and "[Desktop Action Stop]" in text and "--stop" in text
    assert text.count("[Desktop Entry]") == 1


def test_install_writes_executable_entry(tmp_path):
    proj = tmp_path / "proj"
    (proj / "scripts").mkdir(parents=True)
    (proj / "scripts" / "avatargen.sh").write_text("#!/bin/sh\n")
    target = install(proj, tmp_path / "apps")
    assert target.name == "avatar-clip-generator.desktop" and os.access(target, os.X_OK)
    assert "Name=Sprechendes Bild" in target.read_text()


def test_validate_desktop_file_if_tool_available(tmp_path):
    import shutil
    if not shutil.which("desktop-file-validate"):
        return
    proj = tmp_path / "p q"
    (proj / "scripts").mkdir(parents=True)
    (proj / "scripts" / "avatargen.sh").write_text("#!/bin/sh\n")
    (proj / "assets").mkdir()
    (proj / "assets" / "icon.svg").write_text("<svg/>")
    f = install(proj, tmp_path / "apps")
    r = subprocess.run(["desktop-file-validate", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_stop_without_instance(tmp_path, monkeypatch):
    cfg = {"paths": {"work_dir": str(tmp_path)}}
    assert desktop.stop_running(cfg) == 1


def test_port_open_false():
    assert desktop.port_open("127.0.0.1", 1) is False
