"""Classify MIDI channels to GM instrument programs (soundfont-aware)."""

from src.feature_extractor import ChannelFeatures
from src.config import get_instrument_set


def classify_channel(midi_channel: int, features: ChannelFeatures, soundfont_id: str = "snes") -> int:
    inst = get_instrument_set(soundfont_id)
    leads = inst["leads"]
    pads = inst["pads"]
    basses = inst["basses"]

    # Priority 1: Standard MIDI drum channel
    if midi_channel == 9:
        return 128  # GM Drum Kit

    # Priority 2: Percussion detection on other channels (original heuristics)
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

    # Bass
    if features.pitch_max < 55 and features.pitch_range < 24:
        return basses[midi_channel % len(basses)]

    # Lead
    if features.pitch_min > 60 and features.note_density < 4.0 and features.avg_note_duration > 240:
        return leads[midi_channel % len(leads)]

    # Pad
    if features.avg_note_duration > 960:
        return pads[midi_channel % len(pads)]

    return leads[midi_channel % len(leads)]

