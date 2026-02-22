"""
Evaluation runner — RQ1 content-preservation metrics (Deliverable 5).

Proposal citation:
    main.tex §Evaluation Table 2:
        "Melody contour similarity — Input vs. baseline MIDI — Content preservation"
        "Onset alignment (F-measure / offset) — Note onsets, input vs. baseline — Rhythmic preservation"
    05-evaluation.tex §Quantitative Metrics §Content preservation (input vs. baseline remaster):
        "Applied between the input MIDI and the baseline remaster's MIDI..."
    05-evaluation.tex §Data Plan:
        "Fixed MIDI corpus of game or game-like music, all open-licensed or permissioned."
        "Evaluation set held out from training/tuning."
    Deliverable 5: Documentation and evaluation results.

Usage (from repo root, with backend venv active):
    python scripts/run_evaluation.py --corpus data/eval_corpus
    python scripts/run_evaluation.py --corpus data/eval_corpus --styles snes gba --output results/eval.csv

What it does:
    For every MIDI file in the corpus and every selected console style:
      1. Runs the baseline pipeline → produces remapped MIDI.
      2. Computes melody_contour_similarity(input, remapped).
      3. Computes onset_alignment_fmeasure(input, remapped, tolerance_s=0.05).
      4. Records results per file/style.
    Writes a CSV and prints a summary table.

Audio rendering is NOT run by default (use --render to enable it when FluidSynth + LAME are available).
This keeps eval fast and independent of system audio tools.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    import mido
except ImportError:
    print("ERROR: mido not found. Activate the backend venv first.", file=sys.stderr)
    sys.exit(1)

from src.instrument_mapper import remap_midi
from src.evaluation.melody_similarity import melody_contour_similarity
from src.evaluation.onset_alignment import onset_alignment_fmeasure

VALID_STYLES = ["snes", "gba", "nds", "ps2", "wii"]


def _run_baseline_remap(midi_path: Path, style: str, out_dir: Path) -> Path | None:
    """
    Run MIDI remapping (no audio render) and return the remapped MIDI path.
    Returns None on failure.
    """
    try:
        midi = mido.MidiFile(str(midi_path))
        remapped = remap_midi(midi, soundfont_id=style)
        out_path = out_dir / f"{midi_path.stem}_{style}_remap.mid"
        remapped.save(str(out_path))
        return out_path
    except Exception as exc:
        print(f"  [WARN] Remap failed for {midi_path.name} × {style}: {exc}", file=sys.stderr)
        return None


def evaluate_corpus(
    corpus_dir: Path,
    styles: list[str],
    output_csv: Path | None,
    tolerance_s: float = 0.05,
) -> list[dict]:
    midi_files = sorted(corpus_dir.glob("**/*.mid")) + sorted(corpus_dir.glob("**/*.midi"))
    if not midi_files:
        print(f"ERROR: No .mid/.midi files in {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Corpus: {len(midi_files)} files × {len(styles)} styles = {len(midi_files)*len(styles)} runs")
    print(f"Onset tolerance: {int(tolerance_s*1000)} ms\n")

    rows: list[dict] = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="eval_"))
    total = len(midi_files) * len(styles)
    done = 0

    try:
        for midi_path in midi_files:
            for style in styles:
                done += 1
                print(f"[{done}/{total}] {midi_path.name} × {style} ...", end=" ", flush=True)

                row: dict = {
                    "midi_file": midi_path.name,
                    "style": style,
                    "melody_similarity": "",
                    "onset_precision": "",
                    "onset_recall": "",
                    "onset_f_measure": "",
                    "error": "",
                }

                remapped_path = _run_baseline_remap(midi_path, style, tmp_dir)
                if remapped_path is None:
                    row["error"] = "remap_failed"
                    print("FAILED (remap)")
                    rows.append(row)
                    continue

                try:
                    sim = melody_contour_similarity(midi_path, remapped_path)
                    row["melody_similarity"] = f"{sim:.4f}"
                except Exception as exc:
                    row["melody_similarity"] = "ERROR"
                    row["error"] += f"|melody_sim:{exc}"

                try:
                    onset = onset_alignment_fmeasure(midi_path, remapped_path, tolerance_s)
                    row["onset_precision"] = f"{onset['precision']:.4f}"
                    row["onset_recall"] = f"{onset['recall']:.4f}"
                    row["onset_f_measure"] = f"{onset['f_measure']:.4f}"
                except Exception as exc:
                    row["error"] += f"|onset:{exc}"

                print(
                    f"sim={row['melody_similarity']}  "
                    f"onset_F={row['onset_f_measure']}"
                    + (f"  [WARN: {row['error'].strip('|')}]" if row["error"] else "")
                )
                rows.append(row)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Per-style summary
    print("\n── Content-Preservation Summary ─────────────────────────────────")
    print(f"  {'Style':<6}  {'Melody sim (mean)':<20}  {'Onset F (mean)':<16}")
    print("  " + "─" * 48)
    for style in styles:
        style_rows = [r for r in rows if r["style"] == style and r["melody_similarity"] not in ("", "ERROR")]
        if style_rows:
            avg_sim = sum(float(r["melody_similarity"]) for r in style_rows) / len(style_rows)
            f_rows = [r for r in style_rows if r["onset_f_measure"] not in ("", "ERROR")]
            avg_f = sum(float(r["onset_f_measure"]) for r in f_rows) / len(f_rows) if f_rows else float("nan")
            print(f"  {style.upper():<6}  {avg_sim:<20.4f}  {avg_f:<16.4f}")
        else:
            print(f"  {style.upper():<6}  {'no data':<20}  {'no data':<16}")

    # Write CSV
    if output_csv:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["midi_file", "style", "melody_similarity",
                      "onset_precision", "onset_recall", "onset_f_measure", "error"]
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nFull results written to {output_csv}")

    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Run content-preservation evaluation on a MIDI corpus (RQ1 / Deliverable 5)."
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("data/eval_corpus"),
        help="Directory of evaluation MIDI files (default: data/eval_corpus).",
    )
    parser.add_argument(
        "--styles",
        nargs="+",
        choices=VALID_STYLES,
        default=VALID_STYLES,
        help="Console styles to evaluate (default: all five).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional CSV output path (e.g., results/eval_rq1.csv).",
    )
    parser.add_argument(
        "--tolerance-ms",
        type=float,
        default=50.0,
        help="Onset alignment tolerance in milliseconds (default: 50 ms, per proposal).",
    )
    args = parser.parse_args()

    if not args.corpus.is_dir():
        print(f"ERROR: Corpus directory not found: {args.corpus}", file=sys.stderr)
        print("  Populate data/eval_corpus/ with open-licensed MIDI files then re-run.", file=sys.stderr)
        sys.exit(1)

    evaluate_corpus(args.corpus, args.styles, args.output, tolerance_s=args.tolerance_ms / 1000.0)


if __name__ == "__main__":
    main()
