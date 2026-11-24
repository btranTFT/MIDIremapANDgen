"""Apply validated edits to a remapped MIDI without remapping it again."""

import mido

from src.midi_edits import _extract_note_events


class MidiEditError(ValueError):
    def __init__(self, message: str, code: str = "INVALID_EDIT_OPERATION"):
        super().__init__(message)
        self.code = code


def _integer(operation: dict, field: str, minimum: int, maximum: int | None = None):
    value = operation.get(field)
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise MidiEditError(f"Invalid {field}.")
    return value


def edit_remapped_midi(midi: mido.MidiFile, operations: object) -> mido.MidiFile:
    if not isinstance(operations, list):
        raise MidiEditError("operations must be an array.")
    if len(operations) > 20000:
        raise MidiEditError("At most 20000 operations are allowed.", "TOO_MANY_EDIT_OPERATIONS")

    pairs: dict[str, tuple[int, int, int | None]] = {}
    notes, _, _, _ = _extract_note_events(midi, pairs)
    notes_by_id = {note["id"]: note for note in notes}
    tracks = []
    for track in midi.tracks:
        absolute_tick = 0
        events = []
        for index, message in enumerate(track):
            absolute_tick += message.time
            events.append({"tick": absolute_tick, "order": index, "message": message.copy(), "note_id": None})
        tracks.append(events)
    for note_id, (track_index, start_index, end_index) in pairs.items():
        tracks[track_index][start_index]["note_id"] = note_id
        if end_index is not None:
            tracks[track_index][end_index]["note_id"] = note_id

    deleted = set()
    programs = {}
    for operation in operations:
        if not isinstance(operation, dict) or not isinstance(operation.get("type"), str):
            raise MidiEditError("Each operation must be an object with a type.")
        kind = operation["type"]
        if kind in {"update_note", "delete_note"}:
            allowed = {"type", "note_id"} | ({"pitch", "velocity", "start_tick", "duration_ticks"} if kind == "update_note" else set())
            if set(operation) - allowed or not isinstance(operation.get("note_id"), str) or not operation["note_id"]:
                raise MidiEditError("Invalid note operation.")
            note_id = operation["note_id"]
            if note_id not in pairs or note_id in deleted:
                raise MidiEditError(f"Unknown note ID: {note_id}", "UNKNOWN_NOTE_ID")
            track_index, start_index, end_index = pairs[note_id]
            start_event = tracks[track_index][start_index]
            end_event = tracks[track_index][end_index] if end_index is not None else None
            if kind == "delete_note":
                start_event["deleted"] = True
                if end_event is not None:
                    end_event["deleted"] = True
                deleted.add(note_id)
                continue
            if not set(operation) & {"pitch", "velocity", "start_tick", "duration_ticks"}:
                raise MidiEditError("update_note requires at least one field to update.")
            start_tick = _integer(operation, "start_tick", 0) if "start_tick" in operation else start_event["tick"]
            old_duration = max(1, end_event["tick"] - start_event["tick"]) if end_event is not None else notes_by_id[note_id]["duration_ticks"]
            duration = _integer(operation, "duration_ticks", 1) if "duration_ticks" in operation else old_duration
            changes = {}
            if "pitch" in operation:
                changes["note"] = _integer(operation, "pitch", 0, 127)
            if "velocity" in operation:
                changes["velocity"] = _integer(operation, "velocity", 1, 127)
            start_event["message"] = start_event["message"].copy(**changes)
            start_event["tick"] = start_tick
            if end_event is not None:
                if "pitch" in operation:
                    end_event["message"] = end_event["message"].copy(note=changes["note"])
                if "start_tick" in operation or "duration_ticks" in operation:
                    end_event["tick"] = start_tick + duration
            elif "start_tick" in operation or "duration_ticks" in operation:
                raise MidiEditError("Cannot retime a note without a matching note-off.", "UNPAIRED_NOTE")
        elif kind == "set_channel_program":
            if set(operation) != {"type", "channel", "program"}:
                raise MidiEditError("Invalid set_channel_program operation.")
            channel = _integer(operation, "channel", 0, 15)
            programs[channel] = _integer(operation, "program", 0, 127)
        else:
            raise MidiEditError(f"Unknown operation type: {kind}")

    for channel, program in programs.items():
        inserted = False
        for events in tracks:
            has_notes = any(event["message"].type == "note_on" and event["message"].channel == channel and not event.get("deleted") for event in events)
            initial_program = False
            for event in events:
                message = event["message"]
                if message.type == "program_change" and message.channel == channel:
                    event["message"] = message.copy(program=program)
                    initial_program |= event["tick"] == 0
            if has_notes and not initial_program:
                events.append({"tick": 0, "order": -1, "message": mido.Message("program_change", channel=channel, program=program), "note_id": None})
                inserted = True
            elif initial_program:
                inserted = True
        if not inserted and tracks:
            tracks[0].append({"tick": 0, "order": -1, "message": mido.Message("program_change", channel=channel, program=program), "note_id": None})

    output = mido.MidiFile(type=midi.type, ticks_per_beat=midi.ticks_per_beat)
    for events in tracks:
        events = [event for event in events if not event.get("deleted")]
        end_events = [event for event in events if event["message"].type == "end_of_track"]
        events = [event for event in events if event["message"].type != "end_of_track"]
        events.sort(key=lambda event: (event["tick"], event["order"]))
        active = {}
        for event in events:
            message = event["message"]
            if message.type == "note_on" and message.velocity > 0:
                active.setdefault((message.channel, message.note), []).append(event["note_id"])
            elif message.type == "note_off" or (message.type == "note_on" and message.velocity == 0):
                starts = active.get((message.channel, message.note), [])
                matched = starts.pop() if starts else None
                if matched != event["note_id"]:
                    raise MidiEditError("Edit would change overlapping note pairings.", "AMBIGUOUS_NOTE_EDIT")
        new_track = mido.MidiTrack()
        previous_tick = 0
        for event in events:
            new_track.append(event["message"].copy(time=event["tick"] - previous_tick))
            previous_tick = event["tick"]
        if end_events:
            end_tick = max(previous_tick, *(event["tick"] for event in end_events))
            new_track.append(end_events[-1]["message"].copy(time=end_tick - previous_tick))
        output.tracks.append(new_track)
    return output