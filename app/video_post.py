"""ffmpeg-Nachbearbeitung: Frames -> Video in Audiolänge, Original-WAV muxen."""
import subprocess
from pathlib import Path

from app.audio import _ffmpeg, wav_duration


INTERPOLATE = "minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"


def frames_to_video(frames_dir: Path, fps: int, duration: float, out: Path, out_fps: int | None = None) -> Path:
    """Setzt PNG-Frames (frame_00001.png ...) zu einem Video exakt in Länge `duration` zusammen.
    Ist das Video kürzer, wird das letzte Bild gehalten; ist es länger, wird abgeschnitten.
    Mit out_fps != fps werden Zwischenbilder berechnet (ffmpeg minterpolate, CPU); Länge und Ton-Sync bleiben gleich."""
    chain = f"tpad=stop_mode=clone:stop_duration={duration:.3f}"
    if out_fps and out_fps != fps:
        chain += "," + INTERPOLATE.format(fps=out_fps)
    _ffmpeg([
        "-framerate", str(fps), "-i", str(frames_dir / "frame_%05d.png"),
        "-vf", f"{chain},format=yuv420p",
        "-t", f"{duration:.3f}", "-c:v", "libx264", "-crf", "14", "-preset", "medium", str(out),
    ])
    return out


def mux_audio(video: Path, wav: Path, out: Path, duration: float | None = None) -> Path:
    """Original-WAV ins Video (H.264 bleibt, Audio AAC). Länge = WAV, oder `duration` (Ton wird dann mit Stille
    aufgefüllt, falls er kürzer ist)."""
    pad = ["-af", "apad"] if duration else []
    _ffmpeg(["-i", str(video), "-i", str(wav), "-map", "0:v", "-map", "1:a", *pad,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration or wav_duration(wav):.3f}",
             "-movflags", "+faststart", str(out)])
    return out


def video_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())


def export_mpeg(video: Path, wav: Path, out: Path, p: dict) -> Path:
    """Spielformat (Profil): MPEG-1 Programmstream mit MP2-Ton, Länge = Länge der WAV."""
    w, h = p["size"]
    out.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(["-i", str(video), "-i", str(wav), "-map", "0:v", "-map", "1:a",
             "-vf", f"scale={w}:{h}:flags=lanczos,format=yuv420p", "-r", str(p["fps"]),
             "-c:v", p["video_codec"], "-q:v", str(p["video_qscale"]), "-g", str(p["gop"]),
             "-c:a", p["audio_codec"], "-b:a", p["audio_bitrate"], "-ar", str(p["audio_rate"]),
             "-ac", str(p["audio_channels"]), "-t", f"{wav_duration(wav):.3f}", "-f", p["container"], str(out)])
    return out


def probe_frames(path: Path) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                        "stream=nb_read_frames", "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return int(r.stdout.strip())
    except ValueError:
        raise RuntimeError("Der Eingabe-Clip enthält kein lesbares Video.")


def has_audio(path: Path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return bool(r.stdout.strip())


def prepare_control_clip(src: Path, out: Path, width: int, height: int, fps: int, max_frames: int) -> int:
    """Eingabe-Clip auf Bildrate und Größe bringen (füllend skaliert, mittig beschnitten) und auf die erlaubte
    Länge kürzen. Gibt die nutzbare Bildzahl zurück (4k+1, wie es Wan verlangt)."""
    _ffmpeg(["-i", str(src), "-frames:v", str(max_frames), "-an",
             "-vf", f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1",
             "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(out)])
    n = probe_frames(out)
    usable = ((n - 1) // 4) * 4 + 1
    if usable < 5:
        raise RuntimeError("Der Eingabe-Clip ist zu kurz (mindestens etwa 0,2 s).")
    return usable


def extract_audio(src: Path, out: Path, seconds: float) -> Path | None:
    """Ton des Eingabe-Clips (falls vorhanden) in Clip-Länge als WAV."""
    if not has_audio(src):
        return None
    _ffmpeg(["-i", str(src), "-vn", "-t", f"{seconds:.3f}", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(out)])
    return out
