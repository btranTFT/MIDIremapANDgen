"""Render MIDI files to audio using FluidSynth + LAME."""

import atexit
import subprocess
from pathlib import Path

_fluidsynth_processes: set = set()


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


def convert_to_mp3(wav_path: Path, mp3_path: Path):
    cmd = ["lame", "-V2", str(wav_path), str(mp3_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("LAME not found. Install it to enable MP3 output.")


def render_midi_to_audio(midi_path: Path, soundfont_path: Path, output_format: str = "mp3") -> Path:
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
        "-q",
        "-F", str(wav_abs),
        str(soundfont_abs),
        str(midi_abs),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _fluidsynth_processes.add(proc)
    try:
        proc.communicate(timeout=180)
        if proc.returncode != 0:
            raise RuntimeError("FluidSynth rendering failed.")
    finally:
        _fluidsynth_processes.discard(proc)

    if output_format == "mp3":
        convert_to_mp3(wav_path, output_path)
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

