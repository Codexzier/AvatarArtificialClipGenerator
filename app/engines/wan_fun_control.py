"""Video -> Video mit Wan 2.2 Fun Control 5B über ComfyUI.

Der Eingabe-Clip liefert nur die Bewegung/Struktur (Kanten oder ein fertiges Steuervideo), Inhalt und Stil kommen
aus dem Prompt. Vorlage: offizielle ComfyUI-Vorlage video_wan2_2_5B_fun_control (121 Bilder, 24 fps).
"""
import copy
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.comfy.client import ComfyCancelled, ComfyClient, ComfyOutOfMemory
from app.config import ROOT
from app.engines.base import ProgressFn
from app.engines.frames import cleanup_comfy_output, download_frames
from app.engines.wan_s2v import NEGATIVE_DEFAULT
from app.video_post import frames_to_video

WORKFLOW_FILE = ROOT / "workflows" / "wan22_fun_control_5b.api.json"
CONTROL_MODES = {"canny": "Kanten (aus dem Clip berechnet)", "direct": "Direkt (Clip ist schon ein Steuervideo)"}


@dataclass
class V2VSettings:
    prompt: str
    negative_prompt: str = ""
    width: int = 832
    height: int = 480
    length: int = 121          # Bilder (4k+1)
    steps: int = 20
    cfg: float = 5.0
    seed: int = 0
    control: str = "canny"
    canny_low: float = 0.1
    canny_high: float = 0.6


def build_v2v_workflow(models: dict, s: V2VSettings, video_name: str, ref_name: str | None, prefix: str) -> dict:
    g = copy.deepcopy(json.loads(WORKFLOW_FILE.read_text(encoding="utf-8")))
    g["1"]["inputs"]["unet_name"] = models["unet"]
    g["3"]["inputs"]["clip_name"] = models["clip"]
    g["4"]["inputs"]["vae_name"] = models["vae"]
    g["5"]["inputs"]["text"] = s.prompt
    g["6"]["inputs"]["text"] = s.negative_prompt or NEGATIVE_DEFAULT
    g["7"]["inputs"]["file"] = video_name
    g["9"]["inputs"].update(low_threshold=s.canny_low, high_threshold=s.canny_high)
    g["11"]["inputs"].update(width=s.width, height=s.height, length=s.length)
    if s.control == "direct":
        g["11"]["inputs"]["control_video"] = ["8", 0]
        del g["9"]
    elif s.control != "canny":
        raise ValueError(f"Unbekannte Steuerart: {s.control}")
    if ref_name:
        g["10"]["inputs"]["image"] = ref_name
    else:
        del g["10"], g["11"]["inputs"]["ref_image"]
    g["12"]["inputs"].update(seed=s.seed, steps=s.steps, cfg=s.cfg)
    g["14"]["inputs"]["filename_prefix"] = prefix
    return g


class WanFunControlEngine:
    name = "wan_fun_control_5b"
    fps = 24  # das Modell ist auf 121 Bilder bei 24 fps trainiert

    def __init__(self, models: dict, client: ComfyClient, comfyui_dir: Path | None = None):
        self.models, self.client, self.comfyui_dir = models, client, comfyui_dir

    def cancel(self) -> None:
        self.client.interrupt()

    def generate(self, control_clip: Path, ref_image: Path | None, s: V2VSettings, work_dir: Path,
                 progress: ProgressFn | None = None) -> Path:
        """control_clip ist bereits auf Größe, 24 fps und Länge gebracht. Gibt ein stummes H.264-Video zurück."""
        if not self.client.is_up():
            raise RuntimeError("ComfyUI läuft nicht. Bitte zuerst scripts/start_comfyui.sh starten.")
        work_dir.mkdir(parents=True, exist_ok=True)
        job = uuid.uuid4().hex[:8]
        video_name = self.client.upload(control_clip, f"{job}_control.mp4")
        ref_name = self.client.upload(ref_image, f"{job}_ref{ref_image.suffix}") if ref_image else None
        prefix = f"avatargen/{job}/frame"
        graph = build_v2v_workflow(self.models, s, video_name, ref_name, prefix)

        def on_progress(node: str, value: int, maximum: int):
            if node == "12" and progress:
                progress(0.9 * value / maximum, f"Schritt {value}/{maximum}")

        try:
            if progress:
                progress(0.0, f"Starte ({s.width}x{s.height}, {s.length} Bilder, {s.steps} Schritte)")
            history = self.client.run(graph, on_progress)
            if progress:
                progress(0.93, "Setze Video zusammen")
            frames_dir = work_dir / f"{job}_frames"
            download_frames(self.client, history, frames_dir)
            out = frames_to_video(frames_dir, self.fps, s.length / self.fps, work_dir / f"{job}_v2v_silent.mp4")
            shutil.rmtree(frames_dir, ignore_errors=True)
            cleanup_comfy_output(self.comfyui_dir, prefix)
            if progress:
                progress(1.0, "Fertig")
            return out
        except ComfyOutOfMemory as e:
            raise RuntimeError("Der Grafikspeicher (VRAM) reicht nicht aus. Versuche eine kleinere Auflösung "
                               f"(z. B. 832x480) oder weniger Schritte. ({e})") from e
        except ComfyCancelled:
            raise
        finally:
            self.client.free()
