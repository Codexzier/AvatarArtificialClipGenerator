"""Gradio-Oberfläche. Engines kommen von außen (Pipeline), die UI kennt keine konkrete Engine."""
import json
from pathlib import Path

import gradio as gr

from app.audio import EFFECT_LABELS
from app.comfy.client import ComfyCancelled
from app.history import list_runs
from app.jobs import JobRequest, Pipeline, suggest_resolution
from app.pipeline import AudioTooLongError
from app.sysinfo import memory_hint

QUALITY_LABELS = {"preview": "Vorschau (2 s)", "fast": "Schnell", "normal": "Normal", "high": "Hoch"}
HINT_720 = ("**720p:** deutlich längere Laufzeit und mehr Speicherbedarf. Auf 12 GB VRAM besteht die Gefahr "
            "eines Speicherfehlers; im Zweifel 480p wählen.")


def char_info(text: str, cfg: dict) -> str:
    cps, limit = cfg["limits"]["chars_per_second"], cfg["limits"]["max_audio_seconds"]
    n = len(text or "")
    return f"{n} Zeichen ≈ {n / cps:.1f} s · Richtwert {int(cps * limit)} Zeichen für {limit} s (genau: Probehören)"


THEME = gr.themes.Soft(spacing_size="sm", radius_size="sm", text_size="sm").set(
    input_padding="3px 8px", block_padding="3px 4px", layout_gap="4px",
    block_label_padding="1px 6px", block_title_padding="0 0 1px 0", button_medium_padding="3px 10px")

CSS = """
.gradio-container {max-width: 640px !important; margin: 0 auto !important; font-size: 13px !important;}
.gradio-container .block {padding: 3px 4px !important; min-width: 0 !important;}
.gradio-container .form {gap: 3px !important;}
.gradio-container .row {gap: 6px !important;}
.gradio-container .block-title, .gradio-container label > span {font-size: 11px !important; margin-bottom: 1px !important;}
.gradio-container input, .gradio-container textarea, .gradio-container button {font-size: 12px !important;}
.gradio-container button {min-height: 28px !important; padding: 2px 8px !important;}
.gradio-container .prose p {margin: 0 !important; font-size: 11px !important;}
.gradio-container .tab-wrapper, .gradio-container .tab-container {height: 32px !important;}
.gradio-container .tabitem {padding: 2px 0 !important;}
footer {display: none !important;}
"""


def build_ui(pipeline: Pipeline) -> gr.Blocks:
    cfg = pipeline.cfg
    v = cfg["video"]
    voice_choices = [(f"[{vo.engine}] {vo.label}", vo.id) for vo in pipeline.voices.values()]
    templates = cfg["ui"]["motion_templates"]
    resolutions = list(v["resolutions"])
    effects = [(label, key) for key, label in EFFECT_LABELS.items()]
    qualities = [(QUALITY_LABELS.get(k, k), k) for k in v["quality"]]
    default_voice = voice_choices[0][1] if voice_choices else None

    with gr.Blocks(title="Sprechendes Bild") as demo:
        hint = memory_hint()
        notes = ([f"⚠️ {hint}"] if hint else []) + (
            ["⚠️ Keine Stimmen gefunden: `python scripts/download_piper_voices.py --yes`"] if not voice_choices else [])
        if notes:
            gr.Markdown("  \n".join(notes))

        with gr.Tabs() as tabs:
            with gr.Tab("Erstellen", id="erstellen"):
                with gr.Row():
                    image = gr.Image(label="Bild", type="filepath", height=96, sources=["upload", "clipboard"],
                                     scale=1, show_label=False)
                    with gr.Column(scale=2):
                        text = gr.Textbox(show_label=False, lines=3, max_lines=3, placeholder="Text, den die Figur sagt …")
                        counter = gr.Markdown(char_info("", cfg))
                with gr.Row():
                    voice = gr.Dropdown(voice_choices, value=default_voice, label="Stimme", scale=3)
                    effect = gr.Dropdown(effects, value=cfg["tts"]["effect"], label="Effekt", scale=2)
                with gr.Row():
                    resolution = gr.Dropdown(resolutions, value="480p quer", label="Auflösung", scale=1)
                    quality = gr.Dropdown(qualities, value="fast", label="Qualität", scale=1)
                with gr.Row():
                    listen = gr.Button("🔊 Probehören", scale=2)
                    go = gr.Button("🎬 Erzeugen", variant="primary", scale=3)
                    stop = gr.Button("⏹", variant="stop", scale=1, min_width=40)
                status = gr.Markdown()
                listen_audio = gr.Audio(show_label=False, interactive=False, autoplay=True, visible=False)
                with gr.Accordion("Mehr: Tempo, Seed, Bewegung, Engine", open=False):
                    with gr.Row():
                        speed = gr.Slider(0.6, 1.6, value=cfg["tts"]["speed"], step=0.05, label="Tempo")
                        pause = gr.Slider(0.0, 1.5, value=cfg["tts"]["sentence_pause"], step=0.05,
                                          label="Satzpause (s)")
                    with gr.Row():
                        seed = gr.Number(value=0, precision=0, label="Seed")
                        random_seed = gr.Checkbox(value=True, label="Zufälliger Seed")
                    template = gr.Dropdown(list(templates), value=next(iter(templates)), label="Vorlage")
                    prompt = gr.Textbox(label="Bewegungs-Prompt", lines=2, value=next(iter(templates.values())))
                    engine = gr.Dropdown(list(pipeline.video_engines), value=next(iter(pipeline.video_engines)),
                                         label="Video-Engine")
                res_hint = gr.Markdown()

            with gr.Tab("Ergebnis", id="ergebnis"):
                video = gr.Video(label="Ergebnis", interactive=False, height=280)
                result_info = gr.Markdown()

            with gr.Tab("Verlauf", id="verlauf") as history_tab:
                refresh = gr.Button("Aktualisieren")
                table = gr.Dataframe(headers=["Zeit", "Stufe", "Auflösung", "Seed", "Text"], interactive=False,
                                     max_height=120)
                h_video = gr.Video(label="Clip", interactive=False, height=200)
                with gr.Accordion("settings.json", open=False):
                    h_json = gr.Code(language="json", show_label=False)

        # --- Ereignisse ------------------------------------------------------------------------
        text.change(lambda t: char_info(t, cfg), text, counter)
        template.change(lambda t: templates[t], template, prompt)
        resolution.change(lambda r: HINT_720 if r.startswith("720") else "", resolution, res_hint)
        image.change(lambda p: gr.update(value=suggest_resolution(Path(p), v["resolutions"])) if p
                     else gr.update(), image, resolution)

        def do_listen(t, vid, sp, pa, ef):
            if not (t or "").strip():
                raise gr.Error("Bitte zuerst einen Text eingeben.")
            try:
                r = pipeline.preview_audio(t, vid, sp, pa, ef)
            except AudioTooLongError as e:
                raise gr.Error(str(e))
            except ValueError as e:
                raise gr.Error(str(e))
            return (gr.update(value=str(r.path), visible=True),
                    f"Probe: **{r.duration:.1f} s** (maximal {cfg['limits']['max_audio_seconds']} s)")

        listen.click(do_listen, [text, voice, speed, pause, effect], [listen_audio, status])

        def do_generate(img, t, vid, sp, pa, ef, pr, res, ql, sd, rnd, eng, progress=gr.Progress()):
            if not img:
                raise gr.Error("Bitte ein Bild hochladen.")
            if not (t or "").strip():
                raise gr.Error("Bitte einen Text eingeben.")
            req = JobRequest(Path(img), t, vid, sp, pa, ef, pr, res, ql, None if rnd else int(sd), eng)
            try:
                run_dir, info = pipeline.run(req, lambda f, d: progress(f, desc=d))
            except ComfyCancelled:
                return None, "Abgebrochen.", "Abgebrochen.", gr.Tabs()
            except (AudioTooLongError, ValueError, RuntimeError) as e:
                raise gr.Error(str(e))
            msg = (f"Fertig: `{run_dir.name}` · Seed {info['seed']} · "
                   f"{info['audio_seconds']} s · {info['width']}x{info['height']}")
            return str(run_dir / "video.mp4"), msg, msg, gr.Tabs(selected="ergebnis")

        go.click(do_generate, [image, text, voice, speed, pause, effect, prompt, resolution, quality, seed,
                               random_seed, engine], [video, result_info, status, tabs], concurrency_limit=1, concurrency_id="gpu",
                 show_progress_on=[status])
        stop.click(lambda: pipeline.cancel(), None, None, queue=False)

        def load_history():
            runs = list_runs(pipeline.outputs)
            rows = [[r["name"], r["settings"].get("quality", ""), f"{r['settings'].get('width', '')}x"
                     f"{r['settings'].get('height', '')}", r["settings"].get("seed", ""),
                     (r["settings"].get("text", "") or "")[:80]] for r in runs]
            return rows

        def pick(evt: gr.SelectData):
            runs = list_runs(pipeline.outputs)
            r = runs[evt.index[0]]
            return str(r["video"]), json.dumps(r["settings"], indent=2, ensure_ascii=False, default=str)

        refresh.click(load_history, None, table)
        history_tab.select(load_history, None, table)
        table.select(pick, None, [h_video, h_json])
    return demo
