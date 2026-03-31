"""Render MIDI files to audio using FluidSynth + LAME."""

import atexit
import subprocess
from pathlib import Path

_fluidsynth_processes: set = set()
DEFAULT_FLUIDSYNTH_GAIN = 0.35


def _kill_fluidsynth_processes():
    for proc in list(_fluidsynth_processes):
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        _fluidsynth_processes.discard(proc)


atexit.register(_kill_fluidsynth_processes)


def normalize_loudness(wav_path: Path) -> bool:
    """Apply EBU R128 loudness normalization targeting -14 LUFS / -1 dBTP via ffmpeg.

    Returns True on success, False if ffmpeg is unavailable (render continues
    without normalization — install ffmpeg to enable this step).
    """
    normalized = wav_path.with_stem(wav_path.stem + "_norm")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(wav_path),
        "-af", "loudnorm=I=-14:TP=-1:LRA=11",
        str(normalized),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return False
    except subprocess.CalledProcessError:
        # ffmpeg present but failed — skip normalization rather than abort render
        if normalized.exists():
            normalized.unlink(missing_ok=True)
        return False
    # Replace original with normalized version
    normalized.replace(wav_path)
    return True


def convert_to_mp3(wav_path: Path, mp3_path: Path):
    cmd = ["lame", "-V0", str(wav_path), str(mp3_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=90)
    except FileNotFoundError:
        raise RuntimeError("LAME not found. Install it to enable MP3 output.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("LAME MP3 encode timed out (90 s).")


def render_midi_to_audio(
    midi_path: Path,
    soundfont_path: Path,
    output_format: str = "mp3",
    debug_keep_wav: bool = False,
    synth_gain: float = DEFAULT_FLUIDSYNTH_GAIN,
) -> Path:
    output_path = midi_path.with_suffix(f".{output_format}")
    wav_path = midi_path.with_suffix(".wav")

    soundfont_abs = soundfont_path.resolve()
    midi_abs = midi_path.resolve()
    wav_abs = wav_path.resolve()

    # Quick availability check
    try:
        subprocess.run(["fluidsynth", "-h"], check=False, capture_output=True, text=True, timeout=5)
    except FileNotFoundError:
        raise RuntimeError("FluidSynth not found. Install it to enable audio rendering.")

    cmd = [
        "fluidsynth",
        "-n",
        "-i",
        "-a", "file",
        "-r", "44100",
        "-g", f"{max(0.05, min(2.0, synth_gain)):.3f}",
        "-o", "synth.reverb.active=0",
        "-o", "synth.chorus.active=0",
        "-q",
        "-F", str(wav_abs),
        str(soundfont_abs),
        str(midi_abs),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _fluidsynth_processes.add(proc)
    try:
        proc.communicate(timeout=120)
        if proc.returncode != 0:
            raise RuntimeError("FluidSynth rendering failed.")
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()  # drain pipes so the process fully exits
        raise RuntimeError("FluidSynth timed out (120 s). File may be too large or complex.")
    finally:
        _fluidsynth_processes.discard(proc)

    # Loudness normalization pass (EBU R128, -14 LUFS, -1 dBTP)
    if not normalize_loudness(wav_path):
        import warnings
        warnings.warn(
            "Audio warning: ffmpeg not found. Install it to enable loudness normalization.",
            stacklevel=2,
        )

    if output_format == "mp3":
        convert_to_mp3(wav_path, output_path)
        if not debug_keep_wav:
            try:
                wav_path.unlink()
            except Exception:
                pass
        return output_path
    return wav_path


def check_dependencies() -> dict[str, bool]:
    deps: dict[str, bool] = {"fluidsynth": False, "lame": False}
    try:
        r = subprocess.run(["fluidsynth", "-h"], check=False, capture_output=True, text=True, timeout=5)
        deps["fluidsynth"] = ("FluidSynth" in r.stdout) or ("FluidSynth" in r.stderr)
    except Exception:
        deps["fluidsynth"] = False
    try:
        r = subprocess.run(["lame", "--version"], check=False, capture_output=True, text=True, timeout=5)
        deps["lame"] = (r.returncode == 0)
    except Exception:
        deps["lame"] = False
    return deps


def get_tool_versions() -> dict[str, str]:
    """Return version strings for fluidsynth and lame when available."""
    out: dict[str, str] = {"fluidsynth": "unknown", "lame": "unknown"}
    try:
        r = subprocess.run(
            ["fluidsynth", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        text = (r.stdout or r.stderr or "").strip()
        if text:
            out["fluidsynth"] = text.split("\n")[0].strip() or "unknown"
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["lame", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        text = (r.stdout or r.stderr or "").strip()
        if text:
            out["lame"] = text.split("\n")[0].strip() or "unknown"
    except Exception:
        pass
    return out

