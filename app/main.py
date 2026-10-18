"""Startet die Oberfläche."""
from app.comfy.client import ComfyClient
from app.config import load_config, resolve_path
from app.engines.wan_s2v import WanS2VEngine
from app.jobs import Pipeline
from app.tts.registry import available_engines, discover_voices
from app.ui import CSS, THEME, build_ui


def build_pipeline(cfg: dict) -> Pipeline:
    tts = available_engines()
    voices = discover_voices(tts, resolve_path(cfg["paths"]["voices_dir"]))
    cc, v = cfg["comfyui"], cfg["video"]
    wan = WanS2VEngine(cfg["engines"]["wan_s2v"], ComfyClient(cc["host"], cc["port"]),
                       resolve_path(cfg["paths"]["comfyui_dir"]), v["fps"], v["tail_tolerance_frames"], v["trim_frames"])
    return Pipeline(cfg, tts, voices, {wan.name: wan})


def main():
    cfg = load_config()
    demo = build_ui(build_pipeline(cfg))
    demo.queue(default_concurrency_limit=1)
    demo.launch(server_name=cfg["ui"]["host"], server_port=cfg["ui"]["port"], css=CSS, theme=THEME,
                allowed_paths=[str(resolve_path(cfg["paths"]["outputs_dir"])), str(resolve_path(cfg["paths"]["work_dir"]))])


if __name__ == "__main__":
    main()
