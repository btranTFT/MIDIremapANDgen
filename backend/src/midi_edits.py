"""Utilities for advanced baseline MIDI editing and analysis."""

from __future__ import annotations

import json
import logging

import mido

from src.config import get_all_instruments, get_program_name
from src.feature_extractor import (
    extract_features_from_channel,
    get_active_channels,
    get_channel_programs,
)
from src.instrument_mapper import get_channel_classifications

logger = logging.getLogger(__name__)


def _tempo_map(midi: mido.MidiFile) -> list[tuple[int, int]]:
    """Return absolute-tick tempo changes, including the MIDI default tempo."""
    changes = {0: 500000}
    merged_tick = 0
    for message in mido.merge_tracks(midi.tracks):
        merged_tick += message.time
        if message.type == "set_tempo":
            changes[merged_tick] = message.tempo
    return sorted(changes.items())


def _ticks_to_seconds(ticks: int, ticks_per_beat: int, tempo_changes: list[tuple[int, int]]) -> float:
    seconds = 0.0
    previous_tick = 0
    tempo = tempo_changes[0][1]
    for change_tick, change_tempo in tempo_changes[1:]:
        if change_tick >= ticks:
            break
        seconds += mido.tick2second(change_tick - previous_tick, ticks_per_beat, tempo)
        previous_tick = change_tick
        tempo = change_tempo
    seconds += mido.tick2second(max(0, ticks - previous_tick), ticks_per_beat, tempo)
    return seconds


def _extract_note_events(
    midi: mido.MidiFile,
    event_pairs: dict[str, tuple[int, int, int | None]] | None = None,
) -> tuple[list[dict], float, int, int]:
    """Extract note rectangles from the source MIDI without inventing timing."""
    tempo_changes = _tempo_map(midi)
    notes: list[dict] = []
    note_on_count = 0
    note_off_count = 0
    velocity_zero_note_on_count = 0
    note_sequence = 0
    for track_index, track in enumerate(midi.tracks):
        absolute_tick = 0
        track_name = next(
            (message.name for message in track if message.type == "track_name"),
            f"Track {track_index + 1}",
        )
        programs: dict[int, int | None] = {}
        active: dict[tuple[int, int], list[tuple[int, int, int | None, int]]] = {}
        for event_index, message in enumerate(track):
            absolute_tick += message.time
            if message.type == "program_change":
                programs[message.channel] = message.program
                continue
            if message.type == "note_on":
                if message.velocity > 0:
                    note_on_count += 1
                else:
                    velocity_zero_note_on_count += 1
            elif message.type == "note_off":
                note_off_count += 1
            else:
                continue
            key = (message.channel, message.note)
            if message.type == "note_on" and message.velocity > 0:
                active.setdefault(key, []).append(
                    (absolute_tick, message.velocity, programs.get(message.channel), event_index)
                )
            elif message.type == "note_off" or (
                message.type == "note_on" and message.velocity == 0
            ):
                starts = active.get(key)
                if not starts:
                    continue
                start_tick, velocity, program, start_index = starts.pop()
                start_seconds = _ticks_to_seconds(start_tick, midi.ticks_per_beat, tempo_changes)
                end_seconds = _ticks_to_seconds(absolute_tick, midi.ticks_per_beat, tempo_changes)
                note_id = f"{track_index}-{message.channel}-{message.note}-{start_tick}-{note_sequence}"
                if event_pairs is not None:
                    event_pairs[note_id] = (track_index, start_index, event_index)
                notes.append(
                    {
                        "id": note_id,
                        "track": track_index,
                        "track_name": track_name,
                        "channel": message.channel,
                        "pitch": message.note,
                        "start_tick": start_tick,
                        "duration_ticks": max(1, absolute_tick - start_tick),
                        "start_seconds": round(start_seconds, 6),
                        "duration_seconds": round(max(0.001, end_seconds - start_seconds), 6),
                        "velocity": velocity,
                        "program": program,
                        "instrument_name": get_program_name(program),
                    }
                )
                note_sequence += 1
        track_end = _ticks_to_seconds(absolute_tick, midi.ticks_per_beat, tempo_changes)
        for (channel, pitch), starts in active.items():
            for start_tick, velocity, program, start_index in starts:
                start_seconds = _ticks_to_seconds(start_tick, midi.ticks_per_beat, tempo_changes)
                note_id = f"{track_index}-{channel}-{pitch}-{start_tick}-{note_sequence}"
                if event_pairs is not None:
                    event_pairs[note_id] = (track_index, start_index, None)
                notes.append(
                    {
                        "id": note_id,
                        "track": track_index,
                        "track_name": track_name,
                        "channel": channel,
                        "pitch": pitch,
                        "start_tick": start_tick,
                        "duration_ticks": max(1, absolute_tick - start_tick),
                        "start_seconds": round(start_seconds, 6),
                        "duration_seconds": round(max(0.001, track_end - start_seconds), 6),
                        "velocity": velocity,
                        "program": program,
                        "instrument_name": get_program_name(program),
                    }
                )
                note_sequence += 1
    notes_per_channel: dict[int, int] = {}
    for note in notes:
        notes_per_channel[note["channel"]] = notes_per_channel.get(note["channel"], 0) + 1
    logger.info(
        "MIDI note extraction: tracks=%d note_on=%d note_off=%d "
        "velocity_zero_note_on=%d extracted=%d notes_per_channel=%s",
        len(midi.tracks),
        note_on_count,
        note_off_count,
        velocity_zero_note_on_count,
        len(notes),
        notes_per_channel,
    )
    duration_seconds = float(midi.length)
    tempo = tempo_changes[0][1]
    for message in mido.merge_tracks(midi.tracks):
        if message.type == "set_tempo":
            tempo = message.tempo
            break
    return notes, round(duration_seconds, 6), midi.ticks_per_beat, tempo


def extract_midi_notes(midi: mido.MidiFile) -> list[dict]:
    """Extract matched MIDI note events for visual inspection."""
    notes, _duration_seconds, _ticks_per_beat, _tempo = _extract_note_events(midi)
    return notes


def build_visualization_payload(
    midi: mido.MidiFile,
    soundfont_id: str,
    source: str = "remapped",
) -> dict:
    """Build read-only visualizer data from the exact MIDI being rendered."""
    notes = extract_midi_notes(midi)
    if not notes:
        raise ValueError("MIDI contains no extractable note events")
    programs = get_channel_programs(midi)
    channels_by_id: dict[int, dict] = {}
    for channel in get_active_channels(midi):
        program = programs.get(channel)
        channel_notes = [note for note in notes if note["channel"] == channel]
        channels_by_id[channel] = {
            "channel": channel,
            "instrument_name": get_program_name(program) if program is not None else "Unassigned",
            "program": program,
            "note_count": len(channel_notes),
            "is_drum": channel == 9,
        }
    return {
        "source": source,
        "soundfont": soundfont_id,
        "ticks_per_beat": midi.ticks_per_beat,
        "duration_seconds": float(midi.length),
        "channels": list(channels_by_id.values()),
        "notes": notes,
    }


def build_editor_analysis(
    midi: mido.MidiFile,
    soundfont_id: str,
    source_style: str | None = None,
) -> dict:
    """Build editable per-channel analysis for the advanced baseline UI."""
    preserve_compatible_programs = bool(source_style and source_style == soundfont_id)
    classifications = get_channel_classifications(
        midi,
        soundfont_id=soundfont_id,
        preserve_compatible_programs=preserve_compatible_programs,
    )
    original_programs = get_channel_programs(midi)
    channels: list[dict] = []
    notes = extract_midi_notes(midi)
    duration_seconds = float(midi.length)
    ticks_per_beat = midi.ticks_per_beat
    tempo = _tempo_map(midi)[0][1]
    for channel_num in get_active_channels(midi):
        detected_program, detected_name = classifications.get(
            channel_num,
            (128 if channel_num == 9 else 0, get_program_name(128 if channel_num == 9 else 0)),
        )
        features = extract_features_from_channel(midi, channel_num)
        original_program = original_programs.get(channel_num)
        channels.append(
            {
                "channel": channel_num,
                "is_drum": channel_num == 9,
                "original_program": original_program,
                "original_program_name": (
                    get_program_name(original_program)
                    if original_program is not None
                    else None
                ),
                "mapped_program": detected_program,
                "mapped_program_name": detected_name,
                "note_count": getattr(features, "note_count", 0),
                "pitch_min": getattr(features, "pitch_min", None),
                "pitch_max": getattr(features, "pitch_max", None),
                "avg_velocity": round(getattr(features, "avg_velocity", 0.0), 2)
                if features is not None
                else None,
                "track_name": next(
                    (
                        note["track_name"]
                        for note in notes
                        if note["channel"] == channel_num
                    ),
                    f"Channel {channel_num + 1}",
                ),
                "density": round(
                    getattr(features, "note_density", 0.0) or 0.0,
                    2,
                ),
                "defaults": {
                    "program": None,
                    "transpose": 0,
                    "velocity_scale": 1.0,
                    "volume": None,
                    "pan": None,
                    "mute": False,
                    "solo": False,
                    "preserve_program_changes": True,
                },
            }
        )

    available_programs = [
        {"program": program, "name": get_program_name(program)}
        for program in get_all_instruments(soundfont_id)
        if program != 128
    ]
    return {
        "channels": channels,
        "notes": notes,
        "duration_seconds": duration_seconds,
        "ticks_per_beat": ticks_per_beat,
        "tempo": tempo,
        "available_programs": available_programs,
        "preserve_compatible_programs": preserve_compatible_programs,
    }


def parse_channel_overrides(raw: str | None) -> dict[int, dict]:
    """Parse and validate advanced baseline channel overrides from JSON."""
    if raw is None or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid channel_overrides JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("channel_overrides must be a JSON object keyed by channel number")

    normalized: dict[int, dict] = {}
    for key, value in data.items():
        try:
            channel = int(key)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid channel key: {key!r}") from exc
        if channel < 0 or channel > 15:
            raise ValueError(f"Channel out of range: {channel}")
        if not isinstance(value, dict):
            raise ValueError(f"Override for channel {channel} must be an object")

        program = value.get("program")
        if program in ("", None):
            program = None
        elif not isinstance(program, int) or not 0 <= program <= 127:
            raise ValueError(f"program for channel {channel} must be an integer in [0,127]")

        transpose = int(value.get("transpose", 0))
        if transpose < -24 or transpose > 24:
            raise ValueError(f"transpose for channel {channel} must be in [-24,24]")

        velocity_scale = float(value.get("velocity_scale", 1.0))
        if velocity_scale < 0.0 or velocity_scale > 2.0:
            raise ValueError(f"velocity_scale for channel {channel} must be in [0.0,2.0]")

        volume = value.get("volume")
        if volume in ("", None):
            volume = None
        else:
            volume = int(volume)
            if volume < 0 or volume > 127:
                raise ValueError(f"volume for channel {channel} must be in [0,127]")

        pan = value.get("pan")
        if pan in ("", None):
            pan = None
        else:
            pan = int(pan)
            if pan < 0 or pan > 127:
                raise ValueError(f"pan for channel {channel} must be in [0,127]")

        normalized[channel] = {
            "program": program,
            "transpose": transpose,
            "velocity_scale": velocity_scale,
            "volume": volume,
            "pan": pan,
            "mute": bool(value.get("mute", False)),
            "solo": bool(value.get("solo", False)),
            "preserve_program_changes": bool(value.get("preserve_program_changes", True)),
        }
    return normalized


def apply_channel_overrides(midi: mido.MidiFile, overrides: dict[int, dict]) -> mido.MidiFile:
    """Apply advanced baseline edits to a MIDI file before remapping."""
    if not overrides:
        return midi

    output = mido.MidiFile(ticks_per_beat=midi.ticks_per_beat, type=midi.type)
    solo_channels = {channel for channel, override in overrides.items() if override.get("solo")}

    def is_muted(channel: int) -> bool:
        if solo_channels:
            return channel not in solo_channels
        return bool(overrides.get(channel, {}).get("mute", False))

    for track in midi.tracks:
        new_track = mido.MidiTrack()
        track_channels = sorted(
            {
                msg.channel
                for msg in track
                if hasattr(msg, "channel")
            }
        )

        for channel in track_channels:
            if is_muted(channel):
                continue
            override = overrides.get(channel, {})
            if override.get("volume") is not None:
                new_track.append(
                    mido.Message(
                        "control_change",
                        channel=channel,
                        control=7,
                        value=int(override["volume"]),
                        time=0,
                    )
                )
            if override.get("pan") is not None:
                new_track.append(
                    mido.Message(
                        "control_change",
                        channel=channel,
                        control=10,
                        value=int(override["pan"]),
                        time=0,
                    )
                )
            if (
                channel != 9
                and override.get("program") is not None
                and not override.get("preserve_program_changes", True)
            ):
                new_track.append(
                    mido.Message(
                        "program_change",
                        channel=channel,
                        program=int(override["program"]),
                        time=0,
                    )
                )

        for msg in track:
            if not hasattr(msg, "channel"):
                new_track.append(msg.copy())
                continue

            channel = msg.channel
            if is_muted(channel) and msg.type in {
                "note_on",
                "note_off",
                "control_change",
                "program_change",
                "aftertouch",
                "polytouch",
                "pitchwheel",
            }:
                continue

            override = overrides.get(channel, {})
            new_msg = msg.copy()

            if channel != 9 and msg.type in {"note_on", "note_off"}:
                transpose = int(override.get("transpose", 0))
                new_msg.note = max(0, min(127, msg.note + transpose))
                if msg.type == "note_on" and msg.velocity > 0:
                    scaled_velocity = round(msg.velocity * float(override.get("velocity_scale", 1.0)))
                    new_msg.velocity = max(1, min(127, scaled_velocity))

            if channel != 9 and msg.type == "program_change":
                if override.get("program") is not None and not override.get("preserve_program_changes", True):
                    new_msg.program = int(override["program"])

            if msg.type == "control_change":
                if override.get("volume") is not None and msg.control == 7:
                    new_msg.value = int(override["volume"])
                elif override.get("pan") is not None and msg.control == 10:
                    new_msg.value = int(override["pan"])

            new_track.append(new_msg)

        output.tracks.append(new_track)

    return output