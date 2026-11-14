"""Desktop-Fenster statt Browser-Tab.

Startet ComfyUI (falls nötig) und die Gradio-App im Hintergrund und zeigt sie in einem eigenen Fenster:
1. pywebview (GTK/WebKit), 2. Chromium/Chrome im App-Modus. Beim Schließen des Fensters wird alles beendet,
was dieser Start selbst gestartet hat.
"""
import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")  # alles bleibt lokal

import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from app.comfy.client import ComfyClient
from app.config import ROOT, load_config, resolve_path

TITLE = "Sprechendes Bild"
BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave-browser", "microsoft-edge")
LOADING_HTML = """<body style="font-family:sans-serif;background:#1f1d36;color:#eee;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0"><div style="text-align:center"><h3>Sprechendes Bild</h3>
<p>Starte ComfyUI und die Oberfläche … (beim ersten Mal bis zu einer Minute)</p></div></body>"""
ERROR_HTML = """<body style="font-family:sans-serif;background:#3a1f1f;color:#eee;padding:20px"><h3>Start fehlgeschlagen</h3>
<pre style="white-space:pre-wrap">{msg}</pre></body>"""


def find_browser(which=shutil.which) -> str | None:
    for name in BROWSERS:
        path = which(name)
        if path:
            return path
    return None


def gtk_webview_ok() -> bool:
    """Prüft, ob pywebview mit GTK/WebKit lauffähig ist (System-Pakete python3-gi, gir1.2-webkit2-4.1)."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        try:
            gi.require_version("WebKit2", "4.1")
        except ValueError:
            gi.require_version("WebKit2", "4.0")
        import webview  # noqa: F401
        return True
    except Exception:
        return False


def port_open(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def notify(msg: str) -> None:
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", TITLE, msg], check=False)
    print(msg, file=sys.stderr)


class Backend:
    """ComfyUI-Prozess und Gradio-Server dieses Starts."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.comfy_proc: subprocess.Popen | None = None
        self.demo = None
        ui = cfg["ui"]
        self.url = f"http://{ui['host']}:{ui['port']}"

    def start(self) -> None:
        cc = self.cfg["comfyui"]
        client = ComfyClient(cc["host"], cc["port"])
        work = resolve_path(self.cfg["paths"]["work_dir"])
        work.mkdir(parents=True, exist_ok=True)
        if not client.is_up():
            log = open(work / "comfyui.log", "w")
            self.comfy_proc = subprocess.Popen([str(ROOT / "scripts" / "start_comfyui.sh")], stdout=log,
                                               stderr=subprocess.STDOUT, start_new_session=True)
            for _ in range(180):
                if client.is_up():
                    break
                if self.comfy_proc.poll() is not None:
                    tail = (work / "comfyui.log").read_text(errors="replace")[-1500:]
                    raise RuntimeError(f"ComfyUI wurde beendet:\n{tail}")
                time.sleep(2)
            else:
                raise RuntimeError("ComfyUI antwortet nicht (Zeitüberschreitung). Siehe .work/comfyui.log")
        ui = self.cfg["ui"]
        if port_open(ui["host"], ui["port"]):
            return  # App läuft bereits (zweiter Start): nur ein weiteres Fenster öffnen
        from app.main import build_pipeline, build_v2v
        from app.ui import CSS, THEME, build_ui

        pipeline = build_pipeline(self.cfg)
        self.demo = build_ui(pipeline, build_v2v(self.cfg, pipeline))
        self.demo.queue(default_concurrency_limit=1)
        self.demo.launch(server_name=ui["host"], server_port=ui["port"], prevent_thread_lock=True, inbrowser=False,
                         css=CSS, theme=THEME,
                         allowed_paths=[str(resolve_path(self.cfg["paths"]["outputs_dir"])), str(work)])

    def stop(self) -> None:
        if self.demo is not None:
            try:
                self.demo.close()
            except Exception:
                pass
        if self.comfy_proc and self.comfy_proc.poll() is None:  # gibt auch den VRAM frei
            try:
                os.killpg(self.comfy_proc.pid, signal.SIGTERM)
                self.comfy_proc.wait(timeout=15)
            except Exception:
                self.comfy_proc.kill()


def run_webview(backend: Backend, width: int, height: int) -> None:
    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True  # Download-Knopf des Videos
    window = webview.create_window(TITLE, html=LOADING_HTML, width=width, height=height, min_size=(560, 380))

    def boot():
        try:
            backend.start()
        except Exception as e:
            window.load_html(ERROR_HTML.format(msg=str(e)))
            return
        window.load_url(backend.url)

    webview.start(boot)


def run_browser_app(browser: str, backend: Backend, width: int, height: int) -> None:
    notify("Starte ComfyUI und die Oberfläche …")
    backend.start()
    profile = resolve_path(backend.cfg["paths"]["work_dir"]) / "browser-profile"  # eigenes Profil: Prozess läuft bis zum Schließen
    subprocess.run([browser, f"--app={backend.url}", f"--window-size={width},{height}", f"--user-data-dir={profile}",
                    "--no-first-run", "--no-default-browser-check", "--class=avatargen"], check=False)


def pidfile(cfg: dict) -> Path:
    return resolve_path(cfg["paths"]["work_dir"]) / "app.pid"


def stop_running(cfg: dict) -> int:
    pf = pidfile(cfg)
    if not pf.exists():
        print("Keine laufende Instanz gefunden.")
        return 1
    try:
        os.kill(int(pf.read_text()), signal.SIGTERM)
        print("Beenden angefordert.")
        return 0
    except (ValueError, ProcessLookupError):
        pf.unlink(missing_ok=True)
        print("Keine laufende Instanz gefunden.")
        return 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cfg = load_config()
    if "--stop" in argv:
        return stop_running(cfg)
    w = cfg["ui"]["window"]
    backend = Backend(cfg)
    pf = pidfile(cfg)
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # löst das Aufräumen im finally aus
    try:
        if gtk_webview_ok():
            run_webview(backend, w["width"], w["height"])
        elif (browser := find_browser()):
            run_browser_app(browser, backend, w["width"], w["height"])
        else:
            notify("Weder pywebview (GTK) noch Chromium/Chrome gefunden. Siehe README, Abschnitt Desktop-Anwendung.")
            return 1
    finally:
        backend.stop()
        pf.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
