"""Classify MIDI channels to GM instrument programs (soundfont-aware)."""

from src.feature_extractor import ChannelFeatures
from src.config import get_instrument_set


def _pick(palette: list[int], seed: int) -> int:
    """Deterministically pick from palette using a hash seed for even spread."""
    return palette[abs(seed) % len(palette)]


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
    if (
        features.velocity_std > 30
        and features.note_density > 2.0
        and features.avg_note_duration < 480
        and features.syncopation_score > 0.2
    ):
        return 128

    seed = _palette_seed(midi_channel, features)

    # Bass: low pitch ceiling and narrow range
    if features.pitch_max < 55 and features.pitch_range < 24:
        return _pick(basses, seed)

    # Pad: long sustained notes
    if features.avg_note_duration > 960:
        return _pick(pads, seed)

    # Lead: high-register sparse melody
    if features.pitch_min > 60 and features.note_density < 4.0 and features.avg_note_duration > 240:
        return _pick(leads, seed)

    # Default: treat as lead
    return _pick(leads, seed)

