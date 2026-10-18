"""Speicherprüfung: Hinweis, wenn Swap für die großen Modelle knapp ist."""
from pathlib import Path


def _meminfo(path: str = "/proc/meminfo") -> dict[str, float]:
    out = {}
    for line in Path(path).read_text().splitlines():
        key, _, rest = line.partition(":")
        out[key] = float(rest.split()[0]) / 1024 / 1024  # kB -> GB
    return out


def memory_hint(path: str = "/proc/meminfo") -> str | None:
    try:
        m = _meminfo(path)
    except (OSError, ValueError, IndexError):
        return None
    ram, swap = m.get("MemTotal", 0), m.get("SwapTotal", 0)
    if ram < 48 and swap < 8:
        return (f"Wenig Auslagerungsspeicher: {ram:.0f} GB RAM, {swap:.0f} GB Swap. Die Modelle (ca. 22 GB) "
                "werden in den RAM ausgelagert. Empfehlung: Swap-Datei von 32 GB anlegen.")
    return None
