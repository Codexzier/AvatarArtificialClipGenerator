"""ffmpeg-Nachbearbeitung: Frames -> Video in Audiolänge, Original-WAV muxen."""
import subprocess
from pathlib import Path

from app.audio import _ffmpeg, wav_duration


def frames_to_video(frames_dir: Path, fps: int, duration: float, out: Path) -> Path:
    """Setzt PNG-Frames (frame_00001.png ...) zu einem Video exakt in Länge `duration` zusammen.
    Ist das Video kürzer, wird das letzte Bild gehalten; ist es länger, wird abgeschnitten."""
    _ffmpeg([
        "-framerate", str(fps), "-i", str(frames_dir / "frame_%05d.png"),
        "-vf", f"tpad=stop_mode=clone:stop_duration={duration:.3f},format=yuv420p",
        "-t", f"{duration:.3f}", "-c:v", "libx264", "-crf", "14", "-preset", "medium", str(out),
    ])
    return out


def mux_audio(video: Path, wav: Path, out: Path) -> Path:
    """Original-WAV ins Video (H.264 bleibt, Audio AAC)."""
    _ffmpeg(["-i", str(video), "-i", str(wav), "-map", "0:v", "-map", "1:a",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{wav_duration(wav):.3f}",
             "-movflags", "+faststart", str(out)])
    return out


def video_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())
