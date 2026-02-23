"""Apply GM program changes to MIDI channels based on classification."""

import mido

from src.feature_extractor import extract_features_from_channel, get_active_channels, get_channel_programs
from src.instrument_classifier import classify_channel
from src.config import get_all_instruments


def _nearest_program(original: int, soundfont_id: str) -> int:
    """Map a GM program to the nearest available preset in the soundfont.

    Searches the original program's GM family first (groups of 8), then
    expands outward by family distance until a match is found.
    """
    available_set = set(p for p in get_all_instruments(soundfont_id) if p != 128)
    available = sorted(available_set)
    if not available:
        return 0
    if original in available_set:
        return original
    original_family = original // 8
    for dist in range(1, 16):
        for fam in [original_family - dist, original_family + dist]:
            if 0 <= fam < 16:
                for p in range(fam * 8, fam * 8 + 8):
                    if p in available_set:
                        return p
    return available[0]


def remap_midi(input_midi: mido.MidiFile, soundfont_id: str = "snes") -> mido.MidiFile:
    output_midi = mido.MidiFile(ticks_per_beat=input_midi.ticks_per_beat, type=1)

    active_channels = get_active_channels(input_midi)
    original_programs = get_channel_programs(input_midi)
    channel_programs: dict[int, int] = {}

    for channel_num in active_channels:
        if channel_num == 9:
            channel_programs[channel_num] = 128
            continue
        if channel_num in original_programs:
            orig = original_programs[channel_num]
            channel_programs[channel_num] = _nearest_program(orig, soundfont_id)
        else:
            features = extract_features_from_channel(input_midi, channel_num)
            if features:
                channel_programs[channel_num] = classify_channel(channel_num, features, soundfont_id=soundfont_id)

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
    original_programs = get_channel_programs(midi)

    for channel_num in active_channels:
        if channel_num == 9:
            classifications[channel_num] = (128, get_program_name(128))
            continue
        if channel_num in original_programs:
            prog = _nearest_program(original_programs[channel_num], soundfont_id)
        else:
            features = extract_features_from_channel(midi, channel_num)
            if not features:
                continue
            prog = classify_channel(channel_num, features, soundfont_id=soundfont_id)
        classifications[channel_num] = (prog, get_program_name(prog))
    return classifications

