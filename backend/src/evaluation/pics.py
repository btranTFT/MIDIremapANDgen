"""
Pitch-Interval Contour Similarity (PICS).

Proposal citation:
    main.tex §Evaluation, Table 2: "Pitch-interval contour similarity —
        Input vs. baseline audio — Content preservation (RQ1)"
    main.tex §Research Question: "Musical identity is operationalised by
        pitch-interval contour similarity [mirex_sms] and onset alignment
        F-measure [bello2005]."
    main.tex §Success Criteria: "pitch-interval contour similarity >= 0.70"
    Reference: MIREX Symbolic Melodic Similarity task (mirex_sms)
    URL: https://www.music-ir.org/mirex/wiki/Symbolic_Melodic_Similarity

Method:
    1. Extract the dominant melody track from each MIDI file (highest mean
       pitch among active non-drum channels).
    2. Compute the signed interval sequence:  I[i] = pitch[i+1] - pitch[i].
    3. Reduce each interval to its contour direction:
           +1 (ascending), 0 (repeated), -1 (descending).
    4. Score the two contour sequences using the normalised Longest Common
       Subsequence (LCS):
           PICS = LCS(Ca, Cb) / max(|Ca|, |Cb|)

Returns a float in [0, 1].
    1.0 = identical contour; 0.0 = no common subsequence.
    Proposal exploratory threshold: >= 0.70.

Comparison with melody_similarity.py:
    melody_similarity.py uses Pearson correlation of raw pitch values.
    PICS uses interval *directions* and LCS, making it transposition-invariant
    and aligned with the MIREX definition the proposal cites.
    Both metrics can be reported; PICS is the primary metric per the proposal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import mido
import numpy as np


# ── Contour extraction ───────────────────────────────────────────────────────


def _extract_melody_pitches(midi: mido.MidiFile) -> list[int]:
    """
    Return the ordered pitch sequence of the dominant melody channel.

    Dominant = active (non-drum) channel with the highest mean pitch.
    Returns [] if no active non-drum channel is found.
    """
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

    dominant = max(channel_notes, key=lambda ch: float(np.mean(channel_notes[ch])))
    return channel_notes[dominant]


def _pitch_to_contour(pitches: list[int]) -> list[int]:
    """
    Convert a pitch sequence to an interval-direction contour.

    Each element is +1 (ascending), 0 (repeated), or -1 (descending).
    Length = len(pitches) - 1.
    """
    if len(pitches) < 2:
        return []
    contour: list[int] = []
    for i in range(len(pitches) - 1):
        diff = pitches[i + 1] - pitches[i]
        if diff > 0:
            contour.append(1)
        elif diff < 0:
            contour.append(-1)
        else:
            contour.append(0)
    return contour


# ── LCS (standard DP) ───────────────────────────────────────────────────────


def _lcs_length(a: Sequence[int], b: Sequence[int]) -> int:
    """
    Return the length of the Longest Common Subsequence of *a* and *b*.

    Uses O(min(|a|, |b|)) space (two-row DP).
    """
    # Ensure b is the shorter sequence for space efficiency
    if len(a) < len(b):
        a, b = b, a
    m, n = len(a), len(b)
    if n == 0:
        return 0

    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, [0] * (n + 1)
    return prev[n]


# ── Public API ───────────────────────────────────────────────────────────────


def pics(
    midi_a: mido.MidiFile | Path | str,
    midi_b: mido.MidiFile | Path | str,
) -> float:
    """
    Compute Pitch-Interval Contour Similarity between two MIDI files.

    PICS = LCS(contour_a, contour_b) / max(|contour_a|, |contour_b|)

    Args:
        midi_a: Reference MIDI (input, before remastering).
        midi_b: Candidate MIDI (remastered output).

    Returns:
        Float in [0.0, 1.0].  Returns 0.0 on degenerate input (empty,
        single-note, no melody channel).
    """
    if not isinstance(midi_a, mido.MidiFile):
        midi_a = mido.MidiFile(str(midi_a))
    if not isinstance(midi_b, mido.MidiFile):
        midi_b = mido.MidiFile(str(midi_b))

    pitches_a = _extract_melody_pitches(midi_a)
    pitches_b = _extract_melody_pitches(midi_b)

    contour_a = _pitch_to_contour(pitches_a)
    contour_b = _pitch_to_contour(pitches_b)

    if not contour_a or not contour_b:
        return 0.0

    lcs_len = _lcs_length(contour_a, contour_b)
    denominator = max(len(contour_a), len(contour_b))
    return lcs_len / denominator


def pics_from_paths(path_a: str | Path, path_b: str | Path) -> float:
    """Convenience wrapper that accepts file paths directly."""
    return pics(Path(path_a), Path(path_b))
