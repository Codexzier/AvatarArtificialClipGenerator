"""Video -> Video: Eingabe-Clip vorbereiten, mit Prompt und Stil neu erzeugen, Ton übernehmen, speichern."""
import random
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import resolve_path
from app.engines.wan_fun_control import V2VSettings, WanFunControlEngine
from app.storage import safe_name, save_run
from app.video_post import extract_audio, mux_audio, prepare_control_clip


@dataclass
class V2VRequest:
    video: Path
    prompt: str
    style: str
    control: str
    resolution: str
    quality: str
    seed: int | None = None
    ref_image: Path | None = None
    keep_audio: bool = True
    name: str = "v2v"


def build_prompt(cfg: dict, prompt: str, style: str) -> tuple[str, str]:
    """Nutzer-Prompt + Stil-Zusatz; Negativ-Prompt aus dem Stil (leer = Standard)."""
    st = cfg["v2v"]["styles"][style]
    positive = ", ".join(p for p in (prompt.strip().rstrip("."), st["prompt"]) if p)
    return positive, st.get("negative", "")


class V2VPipeline:
    def __init__(self, cfg: dict, engine: WanFunControlEngine, lock=None):
        self.cfg, self.engine = cfg, engine
        self.work = resolve_path(cfg["paths"]["work_dir"])
        self.outputs = resolve_path(cfg["paths"]["outputs_dir"])
        self._lock = lock or threading.Lock()  # gemeinsam mit dem Avatar-Generator: immer nur ein GPU-Job

    def cancel(self) -> None:
        self.engine.cancel()

    def run(self, req: V2VRequest, progress=None) -> tuple[Path, dict]:
        report = progress or (lambda f, t: None)
        c = self.cfg["v2v"]
        if not req.prompt.strip():
            raise ValueError("Bitte beschreiben, was im neuen Clip zu sehen sein soll.")
        w, h = c["resolutions"][req.resolution]
        q = c["quality"][req.quality]
        fps = self.engine.fps
        with self._lock:
            self.work.mkdir(parents=True, exist_ok=True)
            job = uuid.uuid4().hex[:8]
            report(0.0, "Bereite Eingabe-Clip vor")
            control = self.work / f"{job}_input.mp4"
            length = prepare_control_clip(req.video, control, w, h, fps, int(c["max_seconds"] * fps) + 1)
            positive, negative = build_prompt(self.cfg, req.prompt, req.style)
            seed = req.seed if req.seed is not None else random.randint(0, 2**32 - 1)
            s = V2VSettings(prompt=positive, negative_prompt=negative, width=w, height=h, length=length,
                            steps=q["steps"], cfg=q["cfg"], seed=seed, control=req.control)
            silent = self.engine.generate(control, req.ref_image, s, self.work, lambda f, t: report(0.03 + 0.95 * f, t))
            seconds = length / fps
            audio = extract_audio(req.video, self.work / f"{job}_audio.wav", seconds) if req.keep_audio else None
            final = mux_audio(silent, audio, self.work / f"{job}_v2v.mp4", seconds) if audio else silent
            name = safe_name(req.name, "v2v")
            info = {**asdict(req), "video": req.video.name, "ref_image": req.ref_image.name if req.ref_image else None,
                    "text": req.prompt, "full_prompt": positive, "negative": negative or "Standard", "seed": seed,
                    "steps": q["steps"], "cfg": q["cfg"], "width": w, "height": h, "fps": fps, "frames": length,
                    "seconds": round(seconds, 2), "quality": req.quality, "filename": f"{name}.mp4",
                    "engine": self.engine.name, "models": self.engine.models}
            extra = {"input.mp4": control}
            if req.ref_image:
                extra[f"referenz{req.ref_image.suffix.lower()}"] = req.ref_image
            run_dir = save_run(self.outputs, final, audio, None, info, name, extra)
            report(1.0, "Fertig")
            return run_dir, info
