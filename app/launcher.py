"""Anwendungsmenü-Eintrag (.desktop) für Linux erzeugen und installieren."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import ROOT

NAME = "Sprechendes Bild"
ENTRY_FILE = "avatar-clip-generator.desktop"


def _quote(arg: str) -> str:
    """Quoting nach der Desktop-Entry-Spezifikation (Leerzeichen, $, `, \\, ", %)."""
    arg = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    return f'"{arg}"'


def desktop_entry(project: Path = ROOT) -> str:
    script = project / "scripts" / "avatargen.sh"
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        f"Name={NAME}",
        "GenericName=KI-Video-Generator",
        "Comment=Lokaler Generator für sprechende Bilder (Talking Head)",
        f"Exec={_quote(str(script))}",
        f"Icon={project / 'assets' / 'icon.svg'}",
        f"Path={project}",
        "Terminal=false",
        "Categories=AudioVideo;Video;Graphics;",
        "StartupWMClass=avatargen",
        "Actions=Stop;",
        "",
        "[Desktop Action Stop]",
        "Name=Beenden (ComfyUI und App stoppen)",
        f"Exec={_quote(str(script))} --stop",
        "",
    ])


def install(project: Path = ROOT, apps_dir: Path | None = None) -> Path:
    apps = apps_dir or Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    target = apps / ENTRY_FILE
    target.write_text(desktop_entry(project), encoding="utf-8")
    target.chmod(0o755)
    (project / "scripts" / "avatargen.sh").chmod(0o755)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(apps)], check=False)
    return target


if __name__ == "__main__":
    if sys.argv[1:] == ["install"]:
        print("Eintrag installiert:", install())
    else:
        print(desktop_entry())
