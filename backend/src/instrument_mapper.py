"""Apply GM program changes to MIDI channels based on classification."""

import mido

from src.feature_extractor import (
    extract_features_from_channel,
    get_active_channels,
    get_channel_programs,
)
from src.instrument_classifier import classify_channel
from src.config import get_all_instruments


# ---------------------------------------------------------------------------
# Timbre-similarity groups: clusters of GM programs that share perceived
# timbral characteristics, allowing cross-family fallback when the exact
# program is unavailable.
# ---------------------------------------------------------------------------
_TIMBRE_GROUPS: dict[str, list[int]] = {
    "piano":        [0, 1, 2, 3, 4, 5, 6, 7],
    "chromatic":    [8, 9, 10, 11, 12, 13, 14, 15],
    "organ":        [16, 17, 18, 19, 20, 21, 22, 23],
    "guitar_ac":    [24, 25, 26, 27, 28, 29],
    "guitar_el":    [30, 31],
    "bass":         [32, 33, 34, 35, 36, 37, 38, 39],
    "strings":      [40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51],
    "ensemble_pad": [52, 53, 54, 55, 88, 89, 90, 91, 92, 93, 94, 95],
    "brass":        [56, 57, 58, 59, 60, 61, 62, 63],
    "reed":         [64, 65, 66, 67, 68, 69, 70, 71],
    "pipe":         [72, 73, 74, 75, 76, 77, 78, 79],
    "synth_lead":   [80, 81, 82, 83, 84, 85, 86, 87],
    "synth_pad":    [88, 89, 90, 91, 92, 93, 94, 95],
    "fx":           [96, 97, 98, 99, 100, 101, 102, 103],
    "ethnic":       [104, 105, 106, 107, 108, 109, 110, 111],
    "percussive":   [112, 113, 114, 115, 116, 117, 118, 119],
    "sfx":          [120, 121, 122, 123, 124, 125, 126, 127],
}

# Reverse lookup: program -> group name
_PROGRAM_TO_GROUP: dict[int, str] = {}
for _grp_name, _progs in _TIMBRE_GROUPS.items():
    for _p in _progs:
        _PROGRAM_TO_GROUP.setdefault(_p, _grp_name)


# ---------------------------------------------------------------------------
# Per-patch velocity scaling: boost programs that are known to render quietly.
# Bass programs (32-39) and some pads get a modest lift.
# ---------------------------------------------------------------------------
_VELOCITY_SCALE: dict[int, float] = {
    32: 1.05,  # Acoustic Bass
    33: 1.05,  # Electric Bass (finger)
    34: 1.05,  # Electric Bass (pick)
    35: 1.08,  # Fretless Bass
    36: 1.05,  # Slap Bass 1
    37: 1.05,  # Slap Bass 2
    38: 1.03,  # Synth Bass 1
    39: 1.03,  # Synth Bass 2
    42: 1.02,  # Cello
    43: 1.02,  # Contrabass
    88: 1.02,  # New Age pad
    89: 1.02,  # Warm pad
    90: 1.02,  # Polysynth pad
    91: 1.02,  # Choir pad
}


def _nearest_program(original: int, soundfont_id: str) -> int:
    """Map a GM program to the nearest available preset in the soundfont.

    Uses timbre-similarity groups so the fallback preferentially picks a
    program that *sounds* similar rather than one that is merely numerically
    close.
    """
    available_set = set(p for p in get_all_instruments(soundfont_id) if p != 128)
    available = sorted(available_set)
    if not available:
        return 0
    if original in available_set:
        return original

    # 1) Try same timbre group first
    group_name = _PROGRAM_TO_GROUP.get(original)
    if group_name:
        group_progs = _TIMBRE_GROUPS[group_name]
        # Prefer the closest program within the same timbre group
        candidates = [p for p in group_progs if p in available_set]
        if candidates:
            return min(candidates, key=lambda p: abs(p - original))

    # 2) Search related timbre groups by numeric proximity of the original
    #    program to each group's member list.
    best: int | None = None
    best_dist = 999
    for progs in _TIMBRE_GROUPS.values():
        for p in progs:
            if p in available_set and abs(p - original) < best_dist:
                best_dist = abs(p - original)
                best = p
    if best is not None:
        return best

    return available[0]


def _resolve_program(original: int, soundfont_id: str, preserve_compatible: bool = False) -> int:
    """Resolve a program number for the target soundfont.

    In preservation mode, exact compatible programs are retained as-is and only
    incompatible programs fall back to nearest-palette matching.
    """
    if original == 128:
        return 128
    if preserve_compatible:
        available_set = set(p for p in get_all_instruments(soundfont_id) if p != 128)
        if original in available_set:
            return original
    return _nearest_program(original, soundfont_id)


def _scale_velocity(program: int, velocity: int) -> int:
    """Apply per-patch velocity scaling and clamp to [1, 127]."""
    scale = _VELOCITY_SCALE.get(program, 1.0)
    return max(1, min(127, int(velocity * scale)))


def _is_device_sysex(msg: mido.Message) -> bool:
    """Return True for manufacturer-specific SysEx messages (Roland GS, Yamaha XG,
    etc.) that reset hardware state.  These cause FluidSynth to reset all
    channel programs back to 0, overriding our remapped program-change events.
    Universal SysEx (F0 7E / F0 7F) — used for GM reset — is kept.
    """
    if msg.type != "sysex":
        return False
    data = bytes(msg.data)
    if not data:
        return False
    # 0x7E = Universal Non-Realtime, 0x7F = Universal Realtime — keep these
    if data[0] in (0x7E, 0x7F):
        return False
    # Everything else is manufacturer-specific (Roland = 0x41, Yamaha = 0x43, etc.)
    return True


def remap_midi(
    input_midi: mido.MidiFile,
    soundfont_id: str = "snes",
    preserve_compatible_programs: bool = False,
) -> mido.MidiFile:
    # Preserve the source MIDI type.  Forcing type=1 on a type=0 (single-track)
    # input produces a spec-invalid file (type=1 requires ≥2 tracks).  FluidSynth
    # then treats the lone track as the conductor/tempo track and ignores all note
    # data and program changes, causing every channel to fall back to program 0
    # (Acoustic Grand Piano).
    output_midi = mido.MidiFile(ticks_per_beat=input_midi.ticks_per_beat, type=input_midi.type)

    active_channels = get_active_channels(input_midi)
    original_programs = get_channel_programs(input_midi)
    channel_programs: dict[int, int] = {}

    for channel_num in active_channels:
        if channel_num == 9:
            channel_programs[channel_num] = 128
            continue
        if channel_num in original_programs:
            orig = original_programs[channel_num]
            channel_programs[channel_num] = _resolve_program(
                orig,
                soundfont_id,
                preserve_compatible=preserve_compatible_programs,
            )
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

        current_programs = dict(channel_programs)
        for msg in track:
            # Strip device-specific SysEx (Roland GS reset, Yamaha XG reset, etc.)
            # These fire at tick=0 AFTER our program changes and reset all channel
            # programs back to 0, causing every channel to fall back to piano.
            if _is_device_sysex(msg):
                continue

            if msg.type == "program_change" and hasattr(msg, "channel"):
                if msg.channel == 9:
                    current_programs[msg.channel] = 128
                    new_track.append(msg.copy())
                    continue

                mapped_program = _resolve_program(
                    msg.program,
                    soundfont_id,
                    preserve_compatible=preserve_compatible_programs,
                )
                current_programs[msg.channel] = mapped_program
                new_track.append(msg.copy(program=mapped_program))
                continue

            new_msg = msg.copy()
            if hasattr(msg, "channel") and msg.channel in channel_programs:
                prog = current_programs.get(msg.channel, channel_programs[msg.channel])
                if prog == 128 and msg.channel != 9:
                    new_msg.channel = 9
                # Apply per-patch velocity scaling on note_on
                if msg.type == "note_on" and msg.velocity > 0:
                    new_msg.velocity = _scale_velocity(prog, msg.velocity)
            new_track.append(new_msg)

        output_midi.tracks.append(new_track)

    return output_midi


def get_channel_classifications(
    midi: mido.MidiFile,
    soundfont_id: str = "snes",
    preserve_compatible_programs: bool = False,
) -> dict[int, tuple[int, str]]:
    from src.config import get_program_name

    classifications: dict[int, tuple[int, str]] = {}
    active_channels = get_active_channels(midi)
    original_programs = get_channel_programs(midi)

    for channel_num in active_channels:
        if channel_num == 9:
            classifications[channel_num] = (128, get_program_name(128))
            continue
        if channel_num in original_programs:
            prog = _resolve_program(
                original_programs[channel_num],
                soundfont_id,
                preserve_compatible=preserve_compatible_programs,
            )
        else:
            features = extract_features_from_channel(midi, channel_num)
            if not features:
                continue
            prog = classify_channel(channel_num, features, soundfont_id=soundfont_id)
        classifications[channel_num] = (prog, get_program_name(prog))
    return classifications

