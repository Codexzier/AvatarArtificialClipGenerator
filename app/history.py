import json
from pathlib import Path


def list_runs(outputs_dir: Path) -> list[dict]:
    """Bisherige Clips, neueste zuerst."""
    runs = []
    for d in sorted(outputs_dir.glob("*/"), reverse=True) if outputs_dir.is_dir() else []:
        videos, cfg = sorted(d.glob("*.mp4")), d / "settings.json"
        if not videos:
            continue
        video = videos[0]
        try:
            settings = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
        except json.JSONDecodeError:
            settings = {}
        runs.append({"name": d.name, "dir": d, "video": video, "settings": settings})
    return runs
