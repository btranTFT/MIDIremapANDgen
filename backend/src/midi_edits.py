"""Utilities for advanced baseline MIDI editing and analysis."""

from __future__ import annotations

import json

import mido

from src.config import get_all_instruments, get_program_name
from src.feature_extractor import (
    extract_features_from_channel,
    get_active_channels,
    get_channel_programs,
)
from src.instrument_mapper import get_channel_classifications


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