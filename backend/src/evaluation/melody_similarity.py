"""
Melody contour similarity metric.

Proposal citation:
    main.tex §Evaluation, Table 2: "Melody contour similarity — Input vs. baseline MIDI — Content preservation"
    05-evaluation.tex §Quantitative Metrics: "Correlation or distance between pitch contours
    (e.g., normalized pitch sequences or pitch-class histograms) of the dominant melody."
    [CITATION NEEDED: melody contour similarity metric — scholar queries in REVIEWER-CRITIQUE.md §B.6]

Method:
    1. Extract the dominant melody track from each MIDI file (highest-average-pitch active channel,
       excluding channel 9 / drums).
    2. Build a normalized pitch sequence (all note-on events in order, ignoring duration).
    3. Compute Pearson correlation between the two sequences (shortest common prefix).
       Falls back to 0.0 when sequences are empty or have zero variance.

Returns a float in [-1, 1].  1.0 = identical contour; 0.0 = uncorrelated; -1.0 = inverted.
A value ≥ 0.6 is a reasonable exploratory threshold for "contour preserved."
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import mido
import numpy as np


def _extract_melody_pitches(midi: mido.MidiFile) -> list[int]:
    """
    Return the ordered pitch sequence of the dominant melody channel.

    Dominant = active (non-drum) channel with the highest mean pitch.
    Returns [] if no active non-drum channel is found.
    """
    # Collect all note-on events per channel
    channel_notes: dict[int, list[int]] = {}
    for track in midi.tracks:
        for msg in track:
            if (
                hasattr(msg, "channel")
                and msg.type == "note_on"
                and msg.velocity > 0
                and msg.channel != 9  # exclude GM drum channel
            ):
                channel_notes.setdefault(msg.channel, []).append(msg.note)

    if not channel_notes:
        return []

    # Dominant = channel with highest mean pitch (plausible melody proxy)
    dominant = max(channel_notes, key=lambda ch: float(np.mean(channel_notes[ch])))
    return channel_notes[dominant]


def melody_contour_similarity(
    midi_a: mido.MidiFile | Path | str,
    midi_b: mido.MidiFile | Path | str,
) -> float:
    """
    Compute Pearson correlation between the melody pitch contours of two MIDI files.

    Args:
        midi_a: Reference MIDI (mido.MidiFile or file path).
        midi_b: Remastered MIDI (mido.MidiFile or file path).

    Returns:
        Float in [-1.0, 1.0].  Returns 0.0 on degenerate input (empty, constant, very short).
    """
    if not isinstance(midi_a, mido.MidiFile):
        midi_a = mido.MidiFile(str(midi_a))
    if not isinstance(midi_b, mido.MidiFile):
        midi_b = mido.MidiFile(str(midi_b))

    pitches_a = _extract_melody_pitches(midi_a)
    pitches_b = _extract_melody_pitches(midi_b)

    if not pitches_a or not pitches_b:
        return 0.0

    # Align to shortest length for pairwise comparison
    n = min(len(pitches_a), len(pitches_b))
    if n < 2:
        return 0.0

    a = np.array(pitches_a[:n], dtype=float)
    b = np.array(pitches_b[:n], dtype=float)

    # Pearson correlation (returns 0 if variance is 0)
    if np.std(a) == 0 or np.std(b) == 0:
        return 0.0

    corr = float(np.corrcoef(a, b)[0, 1])
    # Guard against NaN from edge cases
    return corr if not np.isnan(corr) else 0.0


def melody_contour_similarity_from_paths(path_a: str | Path, path_b: str | Path) -> float:
    """Convenience wrapper that accepts file paths directly."""
    return melody_contour_similarity(Path(path_a), Path(path_b))
