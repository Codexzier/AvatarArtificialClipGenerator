"""Wan 2.2 S2V (14B) über ComfyUI.

Der Basis-Workflow in workflows/wan22_s2v.api.json enthält einen Chunk. Für längere Clips
hängt build_workflow() weitere WanSoundImageToVideoExtend-Chunks an (wie die offizielle Vorlage).
"""
import copy
import json
import math
import shutil
import uuid
from pathlib import Path

from app.audio import convert_for_engine, wav_duration
from app.comfy.client import ComfyClient, ComfyCancelled, ComfyOutOfMemory, output_files
from app.config import ROOT
from app.engines.base import ProgressFn, VideoEngine, VideoSettings
from app.video_post import frames_to_video

WORKFLOW_FILE = ROOT / "workflows" / "wan22_s2v.api.json"
CHUNK_FRAMES_STEP = 80       # jeder weitere Chunk liefert 20 Latents = 80 Frames

NEGATIVE_DEFAULT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，"
    "JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，"
    "手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)


def chunks_needed(duration: float, fps: int, tolerance_frames: int = 4) -> int:
    """Anzahl Chunks: n Chunks ergeben ca. 80*n - 2 Frames."""
    frames = math.ceil(duration * fps) - tolerance_frames
    return max(1, math.ceil((frames + 2) / CHUNK_FRAMES_STEP))


def build_workflow(models: dict, s: VideoSettings, image_name: str, audio_name: str,
                   chunks: int, frame_prefix: str, trim_frames: int = 3) -> tuple[dict, list[str]]:
    """Setzt Werte in den Basis-Workflow ein. Rückgabe: (Workflow, IDs aller KSampler)."""
    g = copy.deepcopy(json.loads(WORKFLOW_FILE.read_text(encoding="utf-8")))
    g["1"]["inputs"]["unet_name"] = models["unet"]
    if models.get("unet_loader", "unet") == "gguf":  # ComfyUI-GGUF
        g["1"] = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": models["unet"]}}
    g["2"]["inputs"]["lora_name"] = models["lora"]
    if not s.use_lora:
        g["3"]["inputs"]["model"] = ["1", 0]
        del g["2"]
    g["4"]["inputs"]["clip_name"] = models["clip"]
    g["5"]["inputs"]["vae_name"] = models["vae"]
    g["6"]["inputs"]["audio_encoder_name"] = models["audio_encoder"]
    g["7"]["inputs"]["audio"] = audio_name
    g["9"]["inputs"]["image"] = image_name
    g["10"]["inputs"]["text"] = s.prompt
    g["11"]["inputs"]["text"] = s.negative_prompt or NEGATIVE_DEFAULT
    g["12"]["inputs"].update(width=s.width, height=s.height)

    def sampler(inputs: dict) -> dict:
        return {"class_type": "KSampler", "inputs": {
            **inputs, "seed": s.seed, "steps": s.steps, "cfg": s.cfg,
            "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}}

    g["13"] = sampler({k: g["13"]["inputs"][k] for k in ("model", "positive", "negative", "latent_image")})
    samplers, last = ["13"], ["13", 0]
    for k in range(1, chunks):
        ext, smp, cat = f"{20 + 3 * k}", f"{21 + 3 * k}", f"{22 + 3 * k}"
        g[ext] = {"class_type": "WanSoundImageToVideoExtend", "inputs": {
            "positive": ["10", 0], "negative": ["11", 0], "vae": ["5", 0], "length": 77,
            "video_latent": last, "audio_encoder_output": ["8", 0], "ref_image": ["9", 0]}}
        g[smp] = sampler({"model": ["3", 0], "positive": [ext, 0], "negative": [ext, 1], "latent_image": [ext, 2]})
        g[cat] = {"class_type": "LatentConcat", "inputs": {"samples1": last, "samples2": [smp, 0], "dim": "t"}}
        samplers.append(smp)
        last = [cat, 0]
    g["40"]["inputs"]["samples"] = last
    g["41"]["inputs"]["samples2"] = last
    g["43"]["inputs"]["batch_index"] = trim_frames
    g["44"]["inputs"]["filename_prefix"] = frame_prefix
    return g, samplers


class WanS2VEngine(VideoEngine):
    name = "wan_s2v"

    def __init__(self, models: dict, client: ComfyClient, comfyui_dir: Path | None = None,
                 fps: int = 16, tolerance_frames: int = 4, trim_frames: int = 3):
        self.models, self.client, self.comfyui_dir = models, client, comfyui_dir
        self.fps, self.tolerance, self.trim = fps, tolerance_frames, trim_frames

    def cancel(self) -> None:
        self.client.interrupt()

    def generate(self, image: Path, wav: Path, settings: VideoSettings, work_dir: Path,
                 progress: ProgressFn | None = None) -> Path:
        if not self.client.is_up():
            raise RuntimeError("ComfyUI läuft nicht. Bitte zuerst scripts/start_comfyui.sh starten.")
        work_dir.mkdir(parents=True, exist_ok=True)
        job = uuid.uuid4().hex[:8]
        duration = wav_duration(wav)
        wav16 = convert_for_engine(wav, work_dir / f"{job}_16k.wav", 16000, 1)
        chunks = chunks_needed(duration, self.fps, self.tolerance)

        image_name = self.client.upload(image, f"{job}_{image.name}")
        audio_name = self.client.upload(wav16, f"{job}_audio.wav")
        prefix = f"avatargen/{job}/frame"
        graph, samplers = build_workflow(self.models, settings, image_name, audio_name, chunks, prefix, self.trim)

        total = settings.steps * len(samplers)
        done = {}

        def on_progress(node: str, value: int, maximum: int):
            if node in samplers and progress:
                done[node] = value
                part = min(sum(done.values()) / total, 1.0) * 0.95
                n = samplers.index(node) + 1
                progress(part, f"Chunk {n}/{len(samplers)}, Schritt {value}/{maximum}")

        try:
            if progress:
                progress(0.0, f"Starte ({chunks} Chunk{'s' if chunks > 1 else ''}, {settings.steps} Schritte)")
            history = self.client.run(graph, on_progress)
            frames_dir = work_dir / f"{job}_frames"
            frames_dir.mkdir()
            files = output_files(history)
            if not files:
                raise RuntimeError("ComfyUI hat keine Bilder geliefert.")
            for i, f in enumerate(files, 1):
                data = self.client.view(f["filename"], f.get("subfolder", ""), f.get("type", "output"))
                (frames_dir / f"frame_{i:05d}.png").write_bytes(data)
            if progress:
                progress(0.97, "Setze Video zusammen")
            out = frames_to_video(frames_dir, self.fps, duration, work_dir / f"{job}_silent.mp4")
            shutil.rmtree(frames_dir, ignore_errors=True)
            self._cleanup_output(prefix)
            if progress:
                progress(1.0, "Fertig")
            return out
        except ComfyOutOfMemory as e:
            raise RuntimeError(
                "Der Grafikspeicher (VRAM) reicht nicht aus. Versuche eine kleinere Auflösung "
                f"(z. B. 480p) oder eine niedrigere Qualitätsstufe. ({e})") from e
        except ComfyCancelled:
            raise
        finally:
            self.client.free()

    def _cleanup_output(self, prefix: str) -> None:
        if self.comfyui_dir:
            shutil.rmtree(self.comfyui_dir / "output" / Path(prefix).parent, ignore_errors=True)
