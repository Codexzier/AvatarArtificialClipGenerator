"""Ausgabeprofile: "individuell" (frei) oder festes Zielformat, z. B. Avatar Mondschürfer."""
import re
from pathlib import Path

from app.config import resolve_path

INDIVIDUAL = "individuell"
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def profile_choices(cfg: dict) -> list[tuple[str, str]]:
    return [("Individuell", INDIVIDUAL)] + [(p["label"], key) for key, p in cfg.get("profiles", {}).items()]


def get_profile(cfg: dict, key: str) -> dict | None:
    """Profil mit aufgelöster Auflösung (size) oder None bei 'individuell'."""
    if key == INDIVIDUAL or key not in cfg.get("profiles", {}):
        return None
    p = dict(cfg["profiles"][key])
    p["size"] = cfg["video"]["resolutions"][p["resolution"]]
    return p


def clip_id(name: str, default: str = "clip") -> str:
    """Clip-ID als Dateiname: nur a-z, 0-9, _ und -, z. B. clip_capsules_start."""
    name = re.sub(r"\.(mp4|mpg|wav)$", "", (name or "").strip(), flags=re.I).translate(_UMLAUTS)
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_-")
    return name[:80] or default


def export_path(p: dict, name: str, export_dir: str | None = None) -> Path:
    return resolve_path(export_dir or p["export_dir"]) / f"{clip_id(name)}.mpg"
