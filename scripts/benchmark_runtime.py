"""
Runtime benchmarking script — RQ3 (Practical usability).

Proposal citation:
    main.tex §Evaluation Table 2: "Runtime (s) — Baseline and ML runs, per style — Usability (RQ3)"
    05-evaluation.tex §Quantitative Metrics §Runtime:
        "Wall-clock latency (seconds) for baseline remaster and for ML generation,
         per console style, on a fixed hardware setup."
    Deliverable 5: Documentation and evaluation results.

Usage (from repo root, with backend venv active):
    python scripts/benchmark_runtime.py --corpus data/eval_corpus --styles snes gba nds ps2 wii
    python scripts/benchmark_runtime.py --corpus data/eval_corpus --styles snes --output results/runtime.csv

Output:
    CSV with columns: midi_file, style, mode, duration_s, error
    Also prints a summary table to stdout.

Requirements:
    - backend venv active (pip install -r backend/requirements.txt)
    - FluidSynth + LAME on PATH (for baseline)
    - Run from repo root  OR  set PYTHONPATH=backend
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

# Allow running from repo root without installing the package
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from src.instrument_mapper import get_channel_classifications, remap_midi
from src.audio_renderer import render_midi_to_audio, check_dependencies
from src.soundfonts import get_soundfont_path

try:
    import mido
except ImportError:
    print("ERROR: mido not found. Activate the backend venv first.", file=sys.stderr)
    sys.exit(1)

VALID_STYLES = ["snes", "gba", "nds", "ps2", "wii"]


def _benchmark_baseline(midi_path: Path, style: str, tmp_dir: Path) -> tuple[float, str | None]:
    """
    Run the full baseline pipeline for one MIDI file + style.
    Returns (wall_clock_seconds, error_string_or_None).
    """
    import tempfile, shutil

    workspace = tmp_dir / f"{midi_path.stem}_{style}"
    workspace.mkdir(parents=True, exist_ok=True)
    error = None
    t0 = time.monotonic()
    try:
        midi = mido.MidiFile(str(midi_path))
        remapped = remap_midi(midi, soundfont_id=style)
        out_mid = workspace / f"{style}_remap.mid"
        remapped.save(str(out_mid))

        sf_path = get_soundfont_path(style)
        if sf_path.exists():
            render_midi_to_audio(out_mid, sf_path, "mp3")
        else:
            error = f"soundfont not found: {sf_path.name}"
    except Exception as exc:
        error = str(exc)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    elapsed = time.monotonic() - t0
    return elapsed, error


def run_benchmark(
    corpus_dir: Path,
    styles: list[str],
    output_csv: Path | None,
) -> list[dict]:
    deps = check_dependencies()
    if not deps.get("fluidsynth"):
        print("[WARN] FluidSynth not found — audio render steps will be skipped.", file=sys.stderr)
    if not deps.get("lame"):
        print("[WARN] LAME not found — MP3 conversion steps will be skipped.", file=sys.stderr)

    midi_files = sorted(corpus_dir.glob("**/*.mid")) + sorted(corpus_dir.glob("**/*.midi"))
    if not midi_files:
        print(f"ERROR: No .mid/.midi files found in {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    tmp_dir = Path("_bench_tmp")
    tmp_dir.mkdir(exist_ok=True)

    rows: list[dict] = []
    total = len(midi_files) * len(styles)
    done = 0
    for midi_path in midi_files:
        for style in styles:
            done += 1
            print(f"[{done}/{total}] {midi_path.name} × {style} (baseline) ...", end=" ", flush=True)
            elapsed, error = _benchmark_baseline(midi_path, style, tmp_dir)
            status = f"ERROR: {error}" if error else f"{elapsed:.2f}s"
            print(status)
            rows.append({
                "midi_file": midi_path.name,
                "style": style,
                "mode": "baseline",
                "duration_s": f"{elapsed:.3f}",
                "error": error or "",
            })

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # Print summary
    print("\n── Runtime Summary ──────────────────────────────────────────────")
    print(f"{'MIDI file':<30} {'Style':<6} {'Mode':<10} {'Time (s)':>8}  Error")
    print("─" * 70)
    for row in rows:
        print(
            f"{row['midi_file'][:30]:<30} {row['style']:<6} {row['mode']:<10} "
            f"{row['duration_s']:>8}  {row['error'][:40]}"
        )

    # Per-style averages (successful runs only)
    print("\n── Per-style averages (successful runs) ────────────────────────")
    for style in styles:
        style_rows = [r for r in rows if r["style"] == style and not r["error"]]
        if style_rows:
            avg = sum(float(r["duration_s"]) for r in style_rows) / len(style_rows)
            print(f"  {style.upper()}: {avg:.2f}s avg over {len(style_rows)} files")
        else:
            print(f"  {style.upper()}: no successful runs")

    # Write CSV
    if output_csv:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["midi_file", "style", "mode", "duration_s", "error"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nResults written to {output_csv}")

    return rows


def main():
    parser = argparse.ArgumentParser(description="Benchmark baseline pipeline runtime per style (RQ3).")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("data/eval_corpus"),
        help="Directory of .mid/.midi files to benchmark (default: data/eval_corpus).",
    )
    parser.add_argument(
        "--styles",
        nargs="+",
        choices=VALID_STYLES,
        default=VALID_STYLES,
        help="Console styles to benchmark (default: all five).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for CSV output (e.g., results/runtime.csv).",
    )
    args = parser.parse_args()

    if not args.corpus.is_dir():
        print(f"ERROR: Corpus directory not found: {args.corpus}", file=sys.stderr)
        print("  Create it and add open-licensed MIDI files, then re-run.", file=sys.stderr)
        sys.exit(1)

    run_benchmark(args.corpus, args.styles, args.output)


if __name__ == "__main__":
    main()
