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
    return (f"{n} Zeichen, geschätzt ca. {n / cps:.1f} s · Richtwert für {limit} s: ca. {int(cps * limit)} Zeichen "
            "(maßgeblich ist die gemessene Länge beim Probehören)")


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
        gr.Markdown("# Sprechendes Bild\nLokaler Video-Generator: Bild + Text → sprechender Clip.")
        hint = memory_hint()
        if hint:
            gr.Markdown(f"⚠️ {hint}")
        if not voice_choices:
            gr.Markdown("⚠️ Keine Stimmen gefunden. Bitte `python scripts/download_piper_voices.py --yes` ausführen.")

        with gr.Tab("Erstellen"):
            with gr.Row():
                with gr.Column():
                    image = gr.Image(label="Bild (Person oder Roboter)", type="filepath", height=320)
                    text = gr.Textbox(label="Text", lines=4, placeholder="Was soll die Figur sagen?")
                    counter = gr.Markdown(char_info("", cfg))
                    template = gr.Dropdown(list(templates), value=next(iter(templates)), label="Bewegungs-Vorlage")
                    prompt = gr.Textbox(label="Bewegungs-Prompt (frei änderbar)", lines=2,
                                        value=next(iter(templates.values())))
                with gr.Column():
                    gr.Markdown("### Stimme")
                    voice = gr.Dropdown(voice_choices, value=default_voice, label="Stimme (nach Engine gruppiert)")
                    speed = gr.Slider(0.6, 1.6, value=cfg["tts"]["speed"], step=0.05, label="Sprechtempo")
                    pause = gr.Slider(0.0, 1.5, value=cfg["tts"]["sentence_pause"], step=0.05,
                                      label="Pause zwischen Sätzen (s)")
                    effect = gr.Radio(effects, value=cfg["tts"]["effect"], label="Audioeffekt")
                    listen = gr.Button("🔊 Probehören")
                    listen_audio = gr.Audio(label="Probe", interactive=False)
                    listen_info = gr.Markdown()
                    gr.Markdown("### Video")
                    engine = gr.Dropdown(list(pipeline.video_engines), value=next(iter(pipeline.video_engines)),
                                         label="Video-Engine")
                    resolution = gr.Dropdown(resolutions, value="480p quer", label="Auflösung")
                    res_hint = gr.Markdown()
                    quality = gr.Radio(qualities, value="fast", label="Qualitätsstufe")
                    with gr.Row():
                        seed = gr.Number(value=0, precision=0, label="Seed")
                        random_seed = gr.Checkbox(value=True, label="Zufälliger Seed")
            with gr.Row():
                go = gr.Button("🎬 Video erzeugen", variant="primary")
                stop = gr.Button("⏹ Abbrechen", variant="stop")
            video = gr.Video(label="Ergebnis", interactive=False)
            result_info = gr.Markdown()

        with gr.Tab("Verlauf") as history_tab:
            refresh = gr.Button("Aktualisieren")
            table = gr.Dataframe(headers=["Zeit", "Stufe", "Auflösung", "Seed", "Text"], interactive=False)
            h_video = gr.Video(label="Clip", interactive=False)
            h_json = gr.Code(label="settings.json", language="json")

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
            return str(r.path), f"Länge: **{r.duration:.1f} s** (maximal {cfg['limits']['max_audio_seconds']} s)"

        listen.click(do_listen, [text, voice, speed, pause, effect], [listen_audio, listen_info])

        def do_generate(img, t, vid, sp, pa, ef, pr, res, ql, sd, rnd, eng, progress=gr.Progress()):
            if not img:
                raise gr.Error("Bitte ein Bild hochladen.")
            if not (t or "").strip():
                raise gr.Error("Bitte einen Text eingeben.")
            req = JobRequest(Path(img), t, vid, sp, pa, ef, pr, res, ql, None if rnd else int(sd), eng)
            try:
                run_dir, info = pipeline.run(req, lambda f, d: progress(f, desc=d))
            except ComfyCancelled:
                return None, "Abgebrochen."
            except (AudioTooLongError, ValueError, RuntimeError) as e:
                raise gr.Error(str(e))
            return str(run_dir / "video.mp4"), (f"Fertig: `{run_dir.name}` · Seed {info['seed']} · "
                                               f"{info['audio_seconds']} s · {info['width']}x{info['height']}")

        go.click(do_generate, [image, text, voice, speed, pause, effect, prompt, resolution, quality, seed,
                               random_seed, engine], [video, result_info], concurrency_limit=1, concurrency_id="gpu")
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
