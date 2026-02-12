"""Extract features from MIDI channels for classification."""

from dataclasses import dataclass
from typing import Optional

import mido
import numpy as np


@dataclass
class ChannelFeatures:
    channel_num: int
    pitch_min: int
    pitch_max: int
    pitch_range: int
    avg_velocity: float
    velocity_std: float
    note_density: float
    avg_note_duration: float
    note_repeat_rate: float
    percussion_range_ratio: float
    note_count: int
    avg_inter_onset_interval: float
    ioi_std: float
    beat_aligned_ratio: float
    syncopation_score: float


def extract_features_from_channel(midi: mido.MidiFile, midi_channel: int) -> Optional[ChannelFeatures]:
    notes = []
    velocities = []
    durations = []
    onset_times = []
    note_repeats = 0
    percussion_notes = 0
    active_notes: dict[int, tuple[int, int]] = {}

    for track in midi.tracks:
        track_time = 0
        for msg in track:
            track_time += msg.time
            if hasattr(msg, "channel") and msg.channel == midi_channel:
                if msg.type == "note_on" and msg.velocity > 0:
                    notes.append(msg.note)
                    velocities.append(msg.velocity)
                    onset_times.append(track_time)
                    active_notes[msg.note] = (track_time, msg.velocity)
                    if 35 <= msg.note <= 81:
                        percussion_notes += 1
                    if len(notes) > 1 and notes[-1] == notes[-2]:
                        note_repeats += 1
                elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                    if msg.note in active_notes:
                        onset_time, _vel = active_notes[msg.note]
                        durations.append(track_time - onset_time)
                        del active_notes[msg.note]

    if not notes:
        return None

    iois = [onset_times[i + 1] - onset_times[i] for i in range(len(onset_times) - 1)]
    avg_ioi = float(np.mean(iois)) if iois else 0.0
    ioi_std = float(np.std(iois)) if iois else 0.0

    ticks_per_beat = midi.ticks_per_beat
    beat_grid_ticks = ticks_per_beat // 4  # 16th note
    on_grid = sum(1 for t in onset_times if t % beat_grid_ticks < beat_grid_ticks * 0.1)
    beat_aligned_ratio = on_grid / len(onset_times) if onset_times else 0.0

    off_beat_ticks = ticks_per_beat // 2
    syncopated = sum(
        1
        for i, t in enumerate(onset_times)
        if (t % ticks_per_beat) > off_beat_ticks * 0.9 and velocities[i] > 80
    )
    syncopation_score = syncopated / len(onset_times) if onset_times else 0.0

    total_duration_ticks = max(onset_times) if onset_times else 0
    duration_beats = total_duration_ticks / ticks_per_beat if ticks_per_beat > 0 else 1

    return ChannelFeatures(
        channel_num=midi_channel,
        pitch_min=min(notes),
        pitch_max=max(notes),
        pitch_range=max(notes) - min(notes),
        avg_velocity=float(np.mean(velocities)),
        velocity_std=float(np.std(velocities)),
        note_density=len(notes) / duration_beats if duration_beats else float(len(notes)),
        avg_note_duration=float(np.mean(durations)) if durations else 0.0,
        note_repeat_rate=note_repeats / len(notes) if len(notes) > 1 else 0.0,
        percussion_range_ratio=percussion_notes / len(notes),
        note_count=len(notes),
        avg_inter_onset_interval=avg_ioi,
        ioi_std=ioi_std,
        beat_aligned_ratio=beat_aligned_ratio,
        syncopation_score=syncopation_score,
    )


def get_active_channels(midi: mido.MidiFile) -> list[int]:
    channels = set()
    for track in midi.tracks:
        for msg in track:
            if hasattr(msg, "channel") and msg.type in ["note_on", "note_off"]:
                channels.add(msg.channel)
    return sorted(channels)

