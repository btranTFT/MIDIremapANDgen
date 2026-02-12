"""Apply GM program changes to MIDI channels based on classification."""

import mido

from src.feature_extractor import extract_features_from_channel, get_active_channels
from src.instrument_classifier import classify_channel
from src.config import get_all_instruments, is_program_in_soundfont


def _program_for_soundfont(gm_program: int, soundfont_id: str) -> int:
    if is_program_in_soundfont(gm_program, soundfont_id):
        return gm_program
    allowed = get_all_instruments(soundfont_id)
    for p in allowed:
        if p != 128:
            return p
    return allowed[0] if allowed else 0


def remap_midi(input_midi: mido.MidiFile, soundfont_id: str = "snes") -> mido.MidiFile:
    output_midi = mido.MidiFile(ticks_per_beat=input_midi.ticks_per_beat, type=1)

    active_channels = get_active_channels(input_midi)
    channel_programs: dict[int, int] = {}

    for channel_num in active_channels:
        features = extract_features_from_channel(input_midi, channel_num)
        if features:
            gm_program = classify_channel(channel_num, features, soundfont_id=soundfont_id)
            channel_programs[channel_num] = _program_for_soundfont(gm_program, soundfont_id)

    for track in input_midi.tracks:
        new_track = mido.MidiTrack()

        track_channels = set()
        for msg in track:
            if hasattr(msg, "channel"):
                track_channels.add(msg.channel)

        for channel in sorted(track_channels):
            if channel in channel_programs:
                gm_program = channel_programs[channel]
                if gm_program == 128:
                    new_track.append(mido.Message("program_change", program=0, channel=9, time=0))
                else:
                    new_track.append(mido.Message("program_change", program=gm_program, channel=channel, time=0))

        for msg in track:
            new_msg = msg.copy()
            if hasattr(msg, "channel") and msg.channel in channel_programs:
                prog = channel_programs[msg.channel]
                if prog == 128 and msg.channel != 9:
                    new_msg.channel = 9
                if msg.type == "program_change":
                    new_msg.program = 0 if prog == 128 else prog
                    new_msg.channel = 9 if prog == 128 else msg.channel
            new_track.append(new_msg)

        output_midi.tracks.append(new_track)

    return output_midi


def get_channel_classifications(midi: mido.MidiFile, soundfont_id: str = "snes") -> dict[int, tuple[int, str]]:
    from src.config import get_program_name

    classifications: dict[int, tuple[int, str]] = {}
    active_channels = get_active_channels(midi)

    for channel_num in active_channels:
        features = extract_features_from_channel(midi, channel_num)
        if features:
            gm_program = classify_channel(channel_num, features, soundfont_id=soundfont_id)
            classifications[channel_num] = (gm_program, get_program_name(gm_program))
    return classifications

