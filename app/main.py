"""Startet die Oberfläche."""
from app.comfy.client import ComfyClient
from app.config import load_config, resolve_path
from app.engines.wan_fun_control import WanFunControlEngine
from app.engines.wan_s2v import WanS2VEngine
from app.jobs import Pipeline
from app.v2v import V2VPipeline
from app.tts.registry import available_engines, discover_voices
from app.ui import CSS, THEME, build_ui


def build_pipeline(cfg: dict) -> Pipeline:
    tts = available_engines()
    voices = discover_voices(tts, resolve_path(cfg["paths"]["voices_dir"]))
    cc, v = cfg["comfyui"], cfg["video"]
    wan = WanS2VEngine(cfg["engines"]["wan_s2v"], ComfyClient(cc["host"], cc["port"]),
                       resolve_path(cfg["paths"]["comfyui_dir"]), v["fps"], v["tail_tolerance_frames"], v["trim_frames"])
    return Pipeline(cfg, tts, voices, {wan.name: wan})


def build_v2v(cfg: dict, pipeline: Pipeline) -> V2VPipeline | None:
    if "v2v" not in cfg or "engines_v2v" not in cfg:
        return None
    cc = cfg["comfyui"]
    engine = WanFunControlEngine(cfg["engines_v2v"]["wan_fun_control_5b"], ComfyClient(cc["host"], cc["port"]),
                                 resolve_path(cfg["paths"]["comfyui_dir"]))
    return V2VPipeline(cfg, engine, pipeline._lock)  # gemeinsame Sperre: immer nur ein GPU-Job


def main():
    cfg = load_config()
    pipeline = build_pipeline(cfg)
    demo = build_ui(pipeline, build_v2v(cfg, pipeline))
    demo.queue(default_concurrency_limit=1)
    demo.launch(server_name=cfg["ui"]["host"], server_port=cfg["ui"]["port"], css=CSS, theme=THEME,
                allowed_paths=[str(resolve_path(cfg["paths"]["outputs_dir"])), str(resolve_path(cfg["paths"]["work_dir"]))])


if __name__ == "__main__":
    main()
