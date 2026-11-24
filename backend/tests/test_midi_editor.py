import json

import mido
import pytest
from fastapi.testclient import TestClient

from src import api
from src.midi_edits import build_visualization_payload


@pytest.fixture
def edit_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "TEMP_DIR", tmp_path)
    soundfont = tmp_path / "snes.sf2"
    soundfont.touch()
    monkeypatch.setattr(api, "get_soundfont_path", lambda style: soundfont)

    def render(midi_path, soundfont_path, *args):
        assert midi_path.name.startswith("SNESremap_")
        assert "_edited_" in midi_path.name
        output = midi_path.with_suffix(".mp3")
        output.write_bytes(b"mock audio")
        return output

    def no_remap(*args, **kwargs):
        raise AssertionError("Editing must not remap again")

    monkeypatch.setattr(api, "render_midi_to_audio", render)
    monkeypatch.setattr(api, "remap_midi", no_remap)
    workspace = tmp_path / ("a" * 32)
    workspace.mkdir()
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    first = mido.MidiTrack([
        mido.MetaMessage("track_name", name="Lead", time=0),
        mido.MetaMessage("set_tempo", tempo=600000, time=0),
        mido.Message("program_change", channel=0, program=40, time=0),
        mido.Message("control_change", channel=0, control=7, value=80, time=30),
        mido.Message("note_on", channel=0, note=60, velocity=70, time=90),
        mido.Message("pitchwheel", channel=0, pitch=200, time=60),
        mido.Message("note_on", channel=0, note=60, velocity=90, time=60),
        mido.Message("note_on", channel=0, note=60, velocity=0, time=120),
        mido.Message("note_off", channel=0, note=60, velocity=5, time=120),
        mido.MetaMessage("end_of_track", time=0),
    ])
    second = mido.MidiTrack([
        mido.Message("program_change", channel=1, program=20, time=0),
        mido.Message("note_on", channel=1, note=67, velocity=80, time=10),
        mido.Message("note_off", channel=1, note=67, velocity=0, time=240),
        mido.MetaMessage("end_of_track", time=0),
    ])
    midi.tracks.extend([first, second])
    original = workspace / "SNESremap_input.mid"
    midi.save(original)
    uploaded = workspace / "input.mid"
    uploaded.write_bytes(b"original upload must stay untouched")
    (workspace / "metadata.json").write_text(json.dumps({
        "style": "snes", "input_filename": "input.mid", "current_remapped_midi": original.name,
    }))
    notes = build_visualization_payload(mido.MidiFile(original), "snes")["notes"]
    with TestClient(api.app) as client:
        yield client, workspace, original, uploaded, notes


def post_edit(client, workspace, operations):
    return client.post(f"/api/remaster/{workspace.name}/edit", json={"operations": operations})


@pytest.mark.parametrize("field,value", [("pitch", 64), ("velocity", 96), ("start_tick", 500), ("duration_ticks", 240)])
def test_update_note_fields_preserve_original_and_other_events(edit_workspace, field, value):
    client, workspace, original, uploaded, notes = edit_workspace
    target = next(note for note in notes if note["track"] == 1)
    original_bytes = original.read_bytes()
    upload_bytes = uploaded.read_bytes()
    response = post_edit(client, workspace, [{"type": "update_note", "note_id": target["id"], field: value}])
    assert response.status_code == 200, response.text
    result = response.json()
    updated = next(note for note in result["visualization"]["notes"] if note["track"] == 1)
    assert updated[field] == value
    assert original.read_bytes() == original_bytes
    assert uploaded.read_bytes() == upload_bytes
    assert result["audio_url"].endswith("SNESremap_input_edited_1.mp3?sf=snes")
    edited = mido.MidiFile(workspace / "SNESremap_input_edited_1.mid")
    assert edited.type == 1 and edited.ticks_per_beat == 480
    assert [(message.type, message.time) for message in edited.tracks[0]] == [
        (message.type, message.time) for message in mido.MidiFile(original).tracks[0]
    ]


def test_delete_overlapping_note_and_edit_multiple_tracks(edit_workspace):
    client, workspace, original, _, notes = edit_workspace
    inner = next(note for note in notes if note["track"] == 0 and note["velocity"] == 90)
    other_track = next(note for note in notes if note["track"] == 1)
    response = post_edit(client, workspace, [
        {"type": "delete_note", "note_id": inner["id"]},
        {"type": "update_note", "note_id": other_track["id"], "pitch": 72},
        {"type": "set_channel_program", "channel": 0, "program": 81},
    ])
    assert response.status_code == 200, response.text
    body = response.json()
    assert {(note["pitch"], note["velocity"]) for note in body["visualization"]["notes"]} == {(60, 70), (72, 80)}
    assert body["classifications"]["0"]["program"] == 81
    edited = mido.MidiFile(workspace / "SNESremap_input_edited_1.mid")
    assert not any(msg.type == "note_on" and msg.velocity == 0 for msg in edited.tracks[0])
    assert any(msg.type == "pitchwheel" and msg.pitch == 200 for msg in edited.tracks[0])
    assert any(msg.type == "control_change" and msg.value == 80 for msg in edited.tracks[0])
    assert any(msg.type == "set_tempo" and msg.tempo == 600000 for msg in edited.tracks[0])
    assert original.exists()


def test_successive_edits_use_latest_version(edit_workspace):
    client, workspace, original, _, notes = edit_workspace
    original_bytes = original.read_bytes()
    note = next(note for note in notes if note["track"] == 1)
    first = post_edit(client, workspace, [{"type": "update_note", "note_id": note["id"], "pitch": 72}]).json()
    updated_id = next(item["id"] for item in first["visualization"]["notes"] if item["track"] == 1)
    second_response = post_edit(client, workspace, [{"type": "update_note", "note_id": updated_id, "velocity": 99}])
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    note = next(item for item in second["visualization"]["notes"] if item["track"] == 1)
    assert (note["pitch"], note["velocity"]) == (72, 99)
    assert second["midi_url"].endswith("SNESremap_input_edited_2.mid")
    assert (workspace / "SNESremap_input_edited_1.mid").exists()
    assert original.read_bytes() == original_bytes


@pytest.mark.parametrize("operation", [
    {"type": "update_note", "pitch": 128},
    {"type": "update_note", "pitch": -1},
    {"type": "update_note", "velocity": 0},
    {"type": "update_note", "velocity": 128},
    {"type": "update_note", "start_tick": -1},
    {"type": "update_note", "duration_ticks": 0},
    {"type": "update_note", "pitch": True},
    {"type": "update_note", "pitch": "64"},
    {"type": "update_note"},
    {"type": "delete_note", "pitch": 60},
])
def test_invalid_note_operations_return_400(edit_workspace, operation):
    client, workspace, original, _, notes = edit_workspace
    before = original.read_bytes()
    operation = {**operation, "note_id": notes[0]["id"]}
    response = post_edit(client, workspace, [operation])
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_EDIT_OPERATION"
    assert original.read_bytes() == before
    assert not list(workspace.glob("*_edited_*.mid"))


@pytest.mark.parametrize("operation", [
    {"type": "set_channel_program", "channel": -1, "program": 0},
    {"type": "set_channel_program", "channel": 16, "program": 0},
    {"type": "set_channel_program", "channel": 0, "program": 128},
    {"type": "unknown"},
    "not an object",
])
def test_malformed_operations_return_400(edit_workspace, operation):
    client, workspace, _, _, _ = edit_workspace
    assert post_edit(client, workspace, [operation]).status_code == 400


def test_unknown_note_and_invalid_requests(edit_workspace):
    client, workspace, _, _, _ = edit_workspace
    response = post_edit(client, workspace, [{"type": "delete_note", "note_id": "missing"}])
    assert response.status_code == 400 and response.json()["code"] == "UNKNOWN_NOTE_ID"
    assert client.post(f"/api/remaster/{workspace.name}/edit", json={"operations": "bad"}).status_code == 400
    assert client.post(f"/api/remaster/{workspace.name}/edit", content="{").status_code == 400
    assert client.post(f"/api/remaster/{workspace.name}/edit", json={"operations": [{}] * 20001}).json()["code"] == "TOO_MANY_EDIT_OPERATIONS"
    response = client.post("/api/remaster/not-valid/edit", json={"operations": []})
    assert response.status_code == 400 and response.json()["code"] == "INVALID_REQUEST_ID"


def test_type_zero_simultaneous_notes_keep_distinct_pairs(edit_workspace):
    client, workspace, original, _, _ = edit_workspace
    midi = mido.MidiFile(type=0, ticks_per_beat=960)
    midi.tracks.append(mido.MidiTrack([
        mido.Message("note_on", channel=3, note=60, velocity=70, time=0),
        mido.Message("note_on", channel=3, note=60, velocity=90, time=0),
        mido.Message("note_on", channel=3, note=60, velocity=0, time=100),
        mido.Message("note_off", channel=3, note=60, velocity=0, time=100),
    ]))
    midi.save(original)
    notes = build_visualization_payload(mido.MidiFile(original), "snes")["notes"]
    target = next(note for note in notes if note["velocity"] == 90)
    response = post_edit(client, workspace, [{"type": "update_note", "note_id": target["id"], "pitch": 64}])
    assert response.status_code == 200, response.text
    result = response.json()
    assert {(note["pitch"], note["velocity"], note["duration_ticks"]) for note in result["visualization"]["notes"]} == {
        (60, 70, 200), (64, 90, 100),
    }
    edited = mido.MidiFile(workspace / "SNESremap_input_edited_1.mid")
    assert edited.type == 0 and edited.ticks_per_beat == 960
    assert any(msg.type == "note_on" and msg.velocity == 0 and msg.note == 64 for msg in edited.tracks[0])


def test_deleting_all_notes_returns_empty_visualization(edit_workspace):
    client, workspace, _, _, notes = edit_workspace
    response = post_edit(client, workspace, [{"type": "delete_note", "note_id": note["id"]} for note in notes])
    assert response.status_code == 200, response.text
    assert response.json()["visualization"]["notes"] == []
    assert response.json()["classifications"] == {}


def test_ambiguous_overlap_rejected_without_writing(edit_workspace):
    client, workspace, original, _, notes = edit_workspace
    inner = next(note for note in notes if note["track"] == 0 and note["velocity"] == 90)
    before = original.read_bytes()
    response = post_edit(client, workspace, [{"type": "update_note", "note_id": inner["id"], "duration_ticks": 500}])
    assert response.status_code == 400
    assert response.json()["code"] == "AMBIGUOUS_NOTE_EDIT"
    assert original.read_bytes() == before
    assert not list(workspace.glob("*_edited_*.mid"))


def test_invalid_or_missing_current_version_does_not_fall_back(edit_workspace):
    client, workspace, _, _, _ = edit_workspace
    metadata_file = workspace / "metadata.json"
    metadata = json.loads(metadata_file.read_text())
    metadata["current_remapped_midi"] = "SNESremap_missing.mid"
    metadata_file.write_text(json.dumps(metadata))
    response = post_edit(client, workspace, [])
    assert response.status_code == 404
    assert response.json()["code"] == "REMAPPED_MIDI_NOT_FOUND"
    metadata["current_remapped_midi"] = "../SNESremap_input.mid"
    metadata_file.write_text(json.dumps(metadata))
    assert post_edit(client, workspace, []).json()["code"] == "INVALID_REMAP_VERSION"


def test_moving_note_preserves_other_messages_absolute_times(edit_workspace):
    client, workspace, original, _, notes = edit_workspace
    inner = next(note for note in notes if note["track"] == 0 and note["velocity"] == 90)
    response = post_edit(client, workspace, [{
        "type": "update_note", "note_id": inner["id"], "pitch": 65,
        "start_tick": 300, "duration_ticks": 200,
    }])
    assert response.status_code == 200, response.text

    def non_note_events(path):
        track = mido.MidiFile(path).tracks[0]
        tick = 0
        result = []
        for message in track:
            tick += message.time
            if message.type not in {"note_on", "note_off", "end_of_track"}:
                result.append((tick, message.copy(time=0)))
        return result

    edited = workspace / "SNESremap_input_edited_1.mid"
    assert non_note_events(original) == non_note_events(edited)
    assert all(message.time >= 0 for message in mido.MidiFile(edited).tracks[0])


def test_render_failure_returns_edited_midi_with_audio_error(edit_workspace, monkeypatch):
    client, workspace, original, _, notes = edit_workspace

    def fail_render(*args):
        raise RuntimeError("mock render failure")

    monkeypatch.setattr(api, "render_midi_to_audio", fail_render)
    response = post_edit(client, workspace, [{"type": "delete_note", "note_id": notes[0]["id"]}])
    assert response.status_code == 200
    assert response.json()["audio_url"] is None
    assert response.json()["audio_error"] == "mock render failure"
    assert (workspace / "SNESremap_input_edited_1.mid").exists()
    assert original.exists()