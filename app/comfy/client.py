"""Schlanker ComfyUI-Client (HTTP + WebSocket)."""
import json
import uuid
from pathlib import Path
from typing import Callable

import requests
import websocket


class ComfyError(Exception):
    pass


class ComfyOutOfMemory(ComfyError):
    pass


class ComfyCancelled(ComfyError):
    pass


ProgressCb = Callable[[str, int, int], None]  # (node_id, value, max)


class ComfyClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8188, ws_factory=None):
        self.http = f"http://{host}:{port}"
        self.ws_url = f"ws://{host}:{port}/ws"
        self.client_id = uuid.uuid4().hex
        self._ws_factory = ws_factory or (lambda url: websocket.create_connection(url, timeout=600))

    # --- einfache Endpunkte -------------------------------------------------
    def is_up(self) -> bool:
        try:
            return requests.get(f"{self.http}/system_stats", timeout=3).ok
        except requests.RequestException:
            return False

    def upload(self, path: Path, name: str | None = None) -> str:
        """Lädt eine Datei (Bild oder Audio) in den input-Ordner von ComfyUI."""
        with open(path, "rb") as f:
            r = requests.post(
                f"{self.http}/upload/image",
                files={"image": (name or path.name, f)},
                data={"overwrite": "true"},
                timeout=60,
            )
        r.raise_for_status()
        return r.json()["name"]

    def history(self, prompt_id: str) -> dict:
        r = requests.get(f"{self.http}/history/{prompt_id}", timeout=30)
        r.raise_for_status()
        return r.json().get(prompt_id, {})

    def view(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        r = requests.get(
            f"{self.http}/view",
            params={"filename": filename, "subfolder": subfolder, "type": type_},
            timeout=120,
        )
        r.raise_for_status()
        return r.content

    def interrupt(self) -> None:
        requests.post(f"{self.http}/interrupt", timeout=10)

    def free(self) -> None:
        """Gibt Modelle und VRAM frei."""
        try:
            requests.post(f"{self.http}/free", json={"unload_models": True, "free_memory": True}, timeout=30)
        except requests.RequestException:
            pass

    # --- Ausführung -----------------------------------------------------------
    def _queue(self, prompt: dict) -> str:
        r = requests.post(f"{self.http}/prompt", json={"prompt": prompt, "client_id": self.client_id}, timeout=30)
        if r.status_code != 200:
            raise ComfyError(f"ComfyUI hat den Workflow abgelehnt: {r.text[:1500]}")
        return r.json()["prompt_id"]

    def run(self, prompt: dict, on_progress: ProgressCb | None = None) -> dict:
        """Startet den Workflow, wartet auf das Ende und gibt die History-Einträge zurück."""
        ws = self._ws_factory(f"{self.ws_url}?clientId={self.client_id}")  # vor dem Queueing verbinden
        try:
            prompt_id = self._queue(prompt)
            while True:
                msg = ws.recv()
                if isinstance(msg, bytes):  # Vorschaubilder
                    continue
                m = json.loads(msg)
                data = m.get("data", {})
                if data.get("prompt_id") not in (None, prompt_id):
                    continue
                kind = m.get("type")
                if kind == "progress" and on_progress:
                    on_progress(str(data.get("node")), data["value"], data["max"])
                elif kind == "executing" and data.get("node") is None:
                    break
                elif kind == "execution_interrupted":
                    raise ComfyCancelled("Der Job wurde abgebrochen.")
                elif kind == "execution_error":
                    text = f"{data.get('exception_type', '')} {data.get('exception_message', '')}"
                    if "OutOfMemory" in text or "out of memory" in text.lower():
                        raise ComfyOutOfMemory(text.strip())
                    raise ComfyError(f"Fehler in Node {data.get('node_type')} ({data.get('node_id')}): {text.strip()}")
        finally:
            ws.close()
        return self.history(prompt_id)


def output_files(history: dict) -> list[dict]:
    """Alle Ausgabedateien (images/gifs/videos) in Ausführungsreihenfolge der Node-IDs."""
    files = []
    for node_id in sorted(history.get("outputs", {}), key=str):
        for key, items in history["outputs"][node_id].items():
            if isinstance(items, list):
                files += [i for i in items if isinstance(i, dict) and "filename" in i]
    return files
