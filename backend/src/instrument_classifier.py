"""Classify MIDI channels to GM instrument programs (soundfont-aware)."""

from src.feature_extractor import ChannelFeatures
from src.config import get_instrument_set


def _pick(palette: list[int], seed: int, features: ChannelFeatures | None = None) -> int:
    """Deterministically pick from palette using a hash seed, biased by
    register when *features* is provided.

    - High register (pitch_mean > 72): prefer the highest-numbered patch
    - Low register  (pitch_mean < 48): prefer the lowest-numbered patch
    - Mid register: pick from the middle of the palette
    """
    if not palette:
        return 0
    if features is None:
        return palette[abs(seed) % len(palette)]

    sorted_palette = sorted(palette)
    n = len(sorted_palette)

    if features.pitch_mean > 72:
        # High register → last third of sorted palette
        idx = max(0, n - 1 - (abs(seed) % max(1, n // 3)))
    elif features.pitch_mean < 48:
        # Low register → first third of sorted palette
        idx = abs(seed) % max(1, n // 3)
    else:
        # Mid register → middle third
        lo = n // 3
        hi = 2 * n // 3
        span = max(1, hi - lo)
        idx = lo + (abs(seed) % span)

    return sorted_palette[min(idx, n - 1)]


def _palette_seed(midi_channel: int, features: ChannelFeatures) -> int:
    """Combine channel number with coarse feature buckets so channels with
    different pitches or densities land on different parts of the palette."""
    pitch_bucket = features.pitch_min // 12        # octave bucket (0-10)
    density_bucket = int(features.note_density)    # notes-per-beat bucket
    dur_bucket = int(features.avg_note_duration // 240)  # quarter-beat bucket
    return midi_channel * 31 + pitch_bucket * 17 + density_bucket * 7 + dur_bucket * 3


def classify_channel(midi_channel: int, features: ChannelFeatures, soundfont_id: str = "snes") -> int:
    inst = get_instrument_set(soundfont_id)
    leads = inst["leads"]
    pads = inst["pads"]
    basses = inst["basses"]

    # Priority 1: Standard MIDI drum channel
    if midi_channel == 9:
        return 128  # GM Drum Kit

    # Priority 2: Percussion detection on other channels
    if (
        features.percussion_range_ratio > 0.7
        and features.note_repeat_rate > 0.3
        and features.ioi_std > 100
        and features.beat_aligned_ratio < 0.6
    ):
        return 128
    # Secondary percussion heuristic — gated with pitch_range < 12 to avoid
    # misfiring on fast arpeggiated melodic channels.
    if (
        features.velocity_std > 30
        and features.note_density > 2.0
        and features.avg_note_duration < 480
        and features.syncopation_score > 0.2
        and features.pitch_range < 12
    ):
        return 128

    seed = _palette_seed(midi_channel, features)

    # Bass: low mean pitch and moderate range (allows passing notes above G3)
    if features.pitch_mean < 55 and features.pitch_range < 36:
        return _pick(basses, seed, features)

    # Pad: long sustained notes, sparse, with real harmonic spread
    if (
        features.avg_note_duration > 960
        and features.note_density < 1.5
        and features.pitch_range > 12
        and features.pitch_min < 65
    ):
        return _pick(pads, seed, features)

    # Harmony: mid-register chordal accompaniment
    harmonies = inst.get("harmonies", leads)
    if (
        45 < features.pitch_mean < 70
        and 1.0 < features.note_density < 5.0
        and features.pitch_range < 30
    ):
        return _pick(harmonies, seed, features)

    # Lead: high-register sparse melody
    if features.pitch_min > 60 and features.note_density < 4.0 and features.avg_note_duration > 240:
        return _pick(leads, seed, features)

    # Default: treat as lead
    return _pick(leads, seed, features)

