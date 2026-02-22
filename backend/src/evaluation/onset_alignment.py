"""
Onset alignment F-measure metric.

Proposal citation:
    main.tex §Evaluation, Table 2: "Onset alignment (F-measure / offset) — Note onsets, input vs. baseline"
    05-evaluation.tex §Quantitative Metrics: "Temporal offset or F-measure of note onsets
    within a fixed tolerance (e.g., 50–100 ms)."
    [CITATION NEEDED: onset alignment evaluation — scholar queries in REVIEWER-CRITIQUE.md §B.6]
    Reference methodology: Bello et al. (2005) \\cite{bello2005} for onset evaluation framework.

Method:
    1. Extract all note-on event times (in seconds) from both MIDI files.
    2. For each onset in the reference set, check whether a matched onset exists in the
       candidate set within `tolerance_s` seconds (greedy one-to-one matching).
    3. Compute precision, recall, and F-measure (harmonic mean of P and R).

Returns a dict {"precision": float, "recall": float, "f_measure": float}.
A typical evaluation tolerance is 50–100 ms (0.05–0.10 s).
"""

from __future__ import annotations

from pathlib import Path

import mido


def _extract_onset_times_seconds(midi: mido.MidiFile) -> list[float]:
    """
    Return sorted list of all note-on onset times in seconds, across all channels.

    Uses mido's built-in tick-to-second conversion via the file's tempo map.
    """
    onsets: list[float] = []
    for track in midi.tracks:
        elapsed_ticks = 0
        elapsed_seconds = 0.0
        tempo = 500_000  # default: 120 BPM
        for msg in track:
            # Convert delta ticks to seconds
            if midi.ticks_per_beat > 0:
                elapsed_seconds += mido.tick2second(msg.time, midi.ticks_per_beat, tempo)
            elapsed_ticks += msg.time

            if msg.type == "set_tempo":
                tempo = msg.tempo
            elif msg.type == "note_on" and msg.velocity > 0:
                onsets.append(elapsed_seconds)

    return sorted(onsets)


def onset_alignment_fmeasure(
    midi_ref: mido.MidiFile | Path | str,
    midi_cand: mido.MidiFile | Path | str,
    tolerance_s: float = 0.05,
) -> dict[str, float]:
    """
    Compute onset alignment precision, recall, and F-measure between two MIDI files.

    Args:
        midi_ref:     Reference MIDI (input, before remastering). Path or mido.MidiFile.
        midi_cand:    Candidate MIDI (remastered output). Path or mido.MidiFile.
        tolerance_s:  Matching window in seconds (default: 50 ms, per proposal).

    Returns:
        dict with keys "precision", "recall", "f_measure" (all floats in [0, 1]).
        Returns all zeros when either file has no note events.
    """
    if not isinstance(midi_ref, mido.MidiFile):
        midi_ref = mido.MidiFile(str(midi_ref))
    if not isinstance(midi_cand, mido.MidiFile):
        midi_cand = mido.MidiFile(str(midi_cand))

    ref_onsets = _extract_onset_times_seconds(midi_ref)
    cand_onsets = _extract_onset_times_seconds(midi_cand)

    zero = {"precision": 0.0, "recall": 0.0, "f_measure": 0.0}
    if not ref_onsets or not cand_onsets:
        return zero

    # Greedy one-to-one matching: for each reference onset find the nearest
    # candidate onset within tolerance, mark both as used.
    matched_ref = [False] * len(ref_onsets)
    matched_cand = [False] * len(cand_onsets)
    true_positives = 0

    for i, ref_t in enumerate(ref_onsets):
        best_j: int | None = None
        best_dist = float("inf")
        for j, cand_t in enumerate(cand_onsets):
            if matched_cand[j]:
                continue
            dist = abs(ref_t - cand_t)
            if dist <= tolerance_s and dist < best_dist:
                best_dist = dist
                best_j = j
        if best_j is not None:
            matched_ref[i] = True
            matched_cand[best_j] = True
            true_positives += 1

    precision = true_positives / len(cand_onsets) if cand_onsets else 0.0
    recall = true_positives / len(ref_onsets) if ref_onsets else 0.0
    if precision + recall > 0:
        f_measure = 2 * precision * recall / (precision + recall)
    else:
        f_measure = 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f_measure": round(f_measure, 4),
    }


def onset_alignment_fmeasure_from_paths(
    path_ref: str | Path,
    path_cand: str | Path,
    tolerance_s: float = 0.05,
) -> dict[str, float]:
    """Convenience wrapper that accepts file paths directly."""
    return onset_alignment_fmeasure(Path(path_ref), Path(path_cand), tolerance_s)
