"""Job-Liste: erst alle Sprachdateien vorbereiten (CPU), dann Video für Video erzeugen (GPU)."""
import dataclasses
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.comfy.client import ComfyCancelled
from app.jobs import JobRequest, Pipeline
from app.pipeline import AudioTooLongError
from app.storage import safe_name

PENDING, AUDIO_OK, RUNNING, DONE, FAILED, CANCELLED = "wartet", "Audio fertig", "läuft", "fertig", "Fehler", "abgebrochen"


@dataclass
class JobItem:
    name: str
    text: str
    status: str = PENDING
    detail: str = ""
    audio: Path | None = None
    result_dir: Path | None = None

    def row(self) -> list[str]:
        status = self.status + (f" – {self.detail}" if self.detail else "")
        return [self.name, self.text, status]


def parse_rows(rows, namer=safe_name) -> list[JobItem]:
    """Tabelle (Dateiname, Text, [Status]) -> Jobs; leere Zeilen entfallen, fehlende Namen werden ergänzt."""
    items, used = [], set()
    for row in rows or []:
        name, text = (str(row[0] or "").strip(), str(row[1] or "").strip()) if len(row) >= 2 else ("", "")
        if not text:
            continue
        base = namer(name, f"clip_{len(items) + 1:03d}")
        unique, n = base, 1
        while unique.lower() in used:
            n += 1
            unique = f"{base}_{n}"
        used.add(unique.lower())
        items.append(JobItem(unique, text))
    return items


def parse_bulk(text: str) -> list[list[str]]:
    """Zeilen im Format 'name | text' (oder nur 'text') -> Tabellenzeilen."""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        name, sep, rest = line.partition("|")
        rows.append([name.strip(), rest.strip()] if sep else ["", line])
    return rows


class BatchRunner:
    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        self.items: list[JobItem] = []
        self.running = False
        self.progress = 0.0
        self.message = ""
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, items: list[JobItem], template: JobRequest, random_seed: bool) -> None:
        if self.running:
            raise RuntimeError("Es läuft bereits eine Liste.")
        self.items, self.running, self.progress, self.message = items, True, 0.0, "Starte"
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(template, random_seed), daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()
        self.pipeline.cancel()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    # --- Ablauf -----------------------------------------------------------------------------
    def _run(self, template: JobRequest, random_seed: bool) -> None:
        engine = self.pipeline.video_engines[template.engine]
        try:
            with self.pipeline._lock:
                self._phase_audio(template)
                self._phase_video(template, random_seed, engine)
        finally:
            engine.keep_models = False
            engine.release()  # Modelle und VRAM erst nach der ganzen Liste freigeben
            for it in self.items:
                if it.status in (PENDING, AUDIO_OK, RUNNING) and self._cancel.is_set():
                    it.status, it.detail = CANCELLED, ""
            self.message = "Abgebrochen" if self._cancel.is_set() else "Liste abgearbeitet"
            self.running = False

    def _phase_audio(self, template: JobRequest) -> None:
        for i, it in enumerate(self.items, 1):
            if self._cancel.is_set():
                return
            self.message = f"Sprache {i}/{len(self.items)}"
            self.progress = 0.1 * (i - 1) / len(self.items)
            try:
                req = dataclasses.replace(template, text=it.text, name=it.name)
                self.pipeline.check_target(req)
                audio = self.pipeline.prepare_audio(req)
                it.audio, it.status, it.detail = audio.path, AUDIO_OK, f"{audio.duration:.1f} s"
            except (AudioTooLongError, ValueError, RuntimeError, FileExistsError) as e:
                it.status, it.detail = FAILED, str(e)

    def _phase_video(self, template: JobRequest, random_seed: bool, engine) -> None:
        todo = [it for it in self.items if it.status == AUDIO_OK]
        for n, it in enumerate(todo, 1):
            if self._cancel.is_set():
                return
            it.status, it.detail = RUNNING, ""
            req = dataclasses.replace(template, text=it.text, name=it.name, seed=None if random_seed else template.seed)

            def report(f, t, n=n, it=it):
                self.progress = 0.1 + 0.9 * ((n - 1) + f) / len(todo)
                self.message = f"Video {n}/{len(todo)}: {t}"
                it.detail = f"{int(f * 100)} %"

            try:
                it.result_dir, _ = self.pipeline.render(req, it.audio, report, keep_models=n < len(todo))
                it.status, it.detail = DONE, ""
            except ComfyCancelled:
                it.status, it.detail = CANCELLED, ""
                self._cancel.set()  # der Rest der Liste wird ebenfalls als abgebrochen markiert
                return
            except (RuntimeError, ValueError, FileExistsError) as e:
                it.status, it.detail = FAILED, str(e)  # nächster Eintrag läuft trotzdem
