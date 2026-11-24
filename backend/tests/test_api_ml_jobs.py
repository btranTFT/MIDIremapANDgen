import asyncio
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from src import api, api_ml, audio_renderer, ml_inference


@pytest.fixture
def ml_client(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(api_ml, "_generation_lock", asyncio.Lock())
    monkeypatch.setattr(api_ml, "_jobs", {})
    monkeypatch.setattr(api_ml, "_job_tasks", set())
    monkeypatch.setattr(api_ml, "get_ml_diagnostics", lambda *args: {"ml_available": True})
    monkeypatch.setattr(api_ml, "get_checkpoint_path", lambda soundfont: None)
    monkeypatch.setattr(api_ml, "get_tool_versions", lambda: {})
    monkeypatch.setattr(api_ml, "get_device_diagnostics", lambda device: {
        "selected_device": device, "cuda_available": False,
        "gpu_name": None, "allocated_memory_bytes": None,
    })

    def convert(source, destination):
        destination.write_bytes(b"mock mp3")

    monkeypatch.setattr(audio_renderer, "convert_to_mp3", convert)
    with TestClient(api.app) as client:
        yield client


class FakeInference:
    model_name = "mock/model"
    checkpoint_loaded = False

    def load_model(self):
        pass

    def generate_from_text(self, output_path, descriptions, duration):
        output_path.write_bytes(b"mock wav")
        return output_path

    def generate_from_audio(self, prompt_path, output_path, descriptions, duration):
        assert prompt_path.exists()
        return self.generate_from_text(output_path, descriptions, duration)


def wait_for_job(client, job_id, statuses=("complete", "failed")):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/remaster_ml/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in statuses:
            return job
        time.sleep(0.01)
    pytest.fail(f"Job {job_id} did not reach {statuses}")


def test_submission_saves_upload_and_job_completes(ml_client, monkeypatch, tmp_path, minimal_midi_path):
    monkeypatch.setattr(api_ml, "get_inference_engine", lambda *args, **kwargs: FakeInference())
    soundfont = tmp_path / "snes.sf2"
    soundfont.touch()
    monkeypatch.setattr(api_ml, "get_soundfont_path", lambda style: soundfont)

    def render(input_path, *args):
        assert input_path.read_bytes() == minimal_midi_path.read_bytes()
        output = input_path.with_suffix(".wav")
        output.write_bytes(b"mock prompt")
        return output

    monkeypatch.setattr(api_ml, "render_midi_to_audio", render)
    response = ml_client.post(
        "/api/remaster_ml/jobs", data={"description": "test", "prompt_mode": "audio"},
        files={"file": ("input.mid", minimal_midi_path.read_bytes(), "audio/midi")},
    )
    assert response.status_code == 202
    submitted = response.json()
    assert submitted["job_id"]
    assert submitted["status"] == "queued"
    assert list(tmp_path.glob("*/input.mid"))[0].read_bytes() == minimal_midi_path.read_bytes()
    job = wait_for_job(ml_client, submitted["job_id"])
    assert job["status"] == "complete"
    assert job["stage"] == "complete"
    assert job["progress"] == 100
    assert job["error"] is None
    assert job["result"]["method"] == "musicgen_ml"
    assert job["result"]["prompt_mode"] == "audio"
    metadata = job["result"]["metadata"]
    timings = metadata["timings_seconds"]
    assert set(timings) == {
        "upload_validation", "queue_wait", "generation_lock_wait", "model_loading",
        "midi_prompt_rendering", "musicgen_generation", "audio_encoding", "total_job",
    }
    assert all(value >= 0 for value in timings.values())
    assert timings["total_job"] >= timings["musicgen_generation"]
    assert metadata["gpu_diagnostics"]["selected_device"] == "cpu"
    assert metadata["gpu_diagnostics"]["allocated_memory_before_bytes"] is None
    metadata_file = tmp_path / job["result"]["request_id"] / "metadata.json"
    assert json.loads(metadata_file.read_text())["timings_seconds"] == timings


def test_unknown_job_returns_404(ml_client):
    response = ml_client.get("/api/remaster_ml/jobs/missing")
    assert response.status_code == 404
    assert response.json()["code"] == "JOB_NOT_FOUND"


def test_failed_job_retains_error_and_cleans_workspace(ml_client, monkeypatch, tmp_path):
    class FailingInference(FakeInference):
        def generate_from_text(self, output_path, descriptions, duration):
            raise RuntimeError("mock generation failed")

    monkeypatch.setattr(api_ml, "get_inference_engine", lambda *args, **kwargs: FailingInference())
    response = ml_client.post("/api/remaster_ml/jobs", data={"description": "test"})
    job = wait_for_job(ml_client, response.json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"]["code"] == "PROCESSING_ERROR"
    assert "mock generation failed" in job["error"]["debug"]
    assert not list(tmp_path.iterdir())


def test_jobs_serialize_model_generation(ml_client, monkeypatch):
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    calls = []

    class BlockingInference(FakeInference):
        def generate_from_text(self, output_path, descriptions, duration):
            calls.append(descriptions[0])
            if descriptions[0] == "first":
                first_entered.set()
                assert release_first.wait(5)
            else:
                second_entered.set()
            return super().generate_from_text(output_path, descriptions, duration)

    monkeypatch.setattr(api_ml, "get_inference_engine", lambda *args, **kwargs: BlockingInference())
    first = ml_client.post("/api/remaster_ml/jobs", data={"description": "first"}).json()["job_id"]
    try:
        assert first_entered.wait(5)
        second = ml_client.post("/api/remaster_ml/jobs", data={"description": "second"}).json()["job_id"]
        waiting = wait_for_job(ml_client, second, statuses=("running",))
        assert waiting["stage"] == "loading_model"
        assert not second_entered.is_set()
    finally:
        release_first.set()
    assert wait_for_job(ml_client, first)["status"] == "complete"
    assert wait_for_job(ml_client, second)["status"] == "complete"
    assert calls == ["first", "second"]


def test_synchronous_endpoint_still_returns_result(ml_client, monkeypatch):
    monkeypatch.setattr(api_ml, "get_inference_engine", lambda *args, **kwargs: FakeInference())
    response = ml_client.post("/api/remaster_ml", data={"description": "test"})
    assert response.status_code == 200
    assert response.json()["method"] == "musicgen_ml"
    assert response.json()["metadata"]["timings_seconds"]["total_job"] >= 0


def test_unavailable_ml_preserves_error_code(ml_client, monkeypatch):
    monkeypatch.setattr(api_ml, "get_ml_diagnostics", lambda *args: {
        "ml_available": False, "ml_reason": "Unavailable", "recommended_action": "Install dependencies"
    })
    for endpoint in ("/api/remaster_ml", "/api/remaster_ml/jobs"):
        response = ml_client.post(endpoint, data={"description": "test"})
        assert response.status_code == 503
        assert response.json()["code"] == "ML_UNAVAILABLE"


def test_job_timeout_preserves_error_code(ml_client, monkeypatch):
    class SlowInference(FakeInference):
        def generate_from_text(self, output_path, descriptions, duration):
            time.sleep(0.05)
            return super().generate_from_text(output_path, descriptions, duration)

    monkeypatch.setattr(api_ml, "_GENERATION_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(api_ml, "get_inference_engine", lambda *args, **kwargs: SlowInference())
    response = ml_client.post("/api/remaster_ml/jobs", data={"description": "test"})
    job = wait_for_job(ml_client, response.json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"]["code"] == "ML_GENERATION_TIMEOUT"


def test_repeated_jobs_reuse_engine_and_isolate_checkpoints(ml_client, monkeypatch, tmp_path):
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    for style in ("snes", "gba"):
        (checkpoint_dir / f"best_model_{style}.pt").touch()
    created = []

    class CachedInference(FakeInference):
        def __init__(self, soundfont, conditioning):
            self.soundfont_id = soundfont
            self.conditioning_type = conditioning
            self.loaded = False
            self.load_count = 0
            created.append(self)

        def load_model(self):
            if not self.loaded:
                self.load_count += 1
                self.loaded = True

    monkeypatch.setattr(ml_inference, "_inference_instances", {})
    monkeypatch.setattr(ml_inference, "MusicGenInference", CachedInference)
    monkeypatch.setattr(ml_inference, "get_model_config", lambda conditioning: {"model_name": "mock"})
    monkeypatch.setattr(ml_inference, "get_checkpoint_path", lambda style: checkpoint_dir / f"best_model_{style}.pt")
    for style in ("snes", "gba", "snes"):
        response = ml_client.post("/api/remaster_ml/jobs", data={"description": "test", "soundfont": style})
        assert wait_for_job(ml_client, response.json()["job_id"])["status"] == "complete"
    assert [engine.soundfont_id for engine in created] == ["snes", "gba"]
    assert [engine.load_count for engine in created] == [1, 1]


def test_failed_generation_releases_lock_and_cuda_cache(ml_client, monkeypatch, tmp_path):
    released = []

    class FailsOnce(FakeInference):
        device = "cuda:0"
        calls = 0

        def generate_from_text(self, output_path, descriptions, duration):
            self.calls += 1
            if self.calls == 1:
                output_path.write_bytes(b"partial")
                raise RuntimeError("CUDA out of memory")
            return super().generate_from_text(output_path, descriptions, duration)

    inference = FailsOnce()
    monkeypatch.setattr(api_ml, "get_inference_engine", lambda *args, **kwargs: inference)
    monkeypatch.setattr(api_ml, "release_cuda_cache", lambda device: released.append(device))
    first = ml_client.post("/api/remaster_ml/jobs", data={"description": "first"}).json()["job_id"]
    failed = wait_for_job(ml_client, first)
    assert failed["status"] == "failed"
    assert "CUDA out of memory" in failed["error"]["debug"]
    assert not list(tmp_path.iterdir())
    second = ml_client.post("/api/remaster_ml/jobs", data={"description": "second"}).json()["job_id"]
    assert wait_for_job(ml_client, second)["status"] == "complete"
    assert released == ["cuda:0"]


def test_model_loading_does_not_block_job_polling(ml_client, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    class SlowLoad(FakeInference):
        def load_model(self):
            entered.set()
            assert release.wait(5)

    monkeypatch.setattr(api_ml, "get_inference_engine", lambda *args, **kwargs: SlowLoad())
    job_id = ml_client.post("/api/remaster_ml/jobs", data={"description": "test"}).json()["job_id"]
    try:
        assert entered.wait(5)
        response = ml_client.get(f"/api/remaster_ml/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["stage"] == "loading_model"
    finally:
        release.set()
    assert wait_for_job(ml_client, job_id)["status"] == "complete"


def test_cuda_memory_samples_are_in_result_metadata(ml_client, monkeypatch):
    class GpuInference(FakeInference):
        device = "cuda:0"

    samples = iter((128, 256))
    monkeypatch.setattr(api_ml, "get_inference_engine", lambda *args, **kwargs: GpuInference())
    monkeypatch.setattr(api_ml, "get_device_diagnostics", lambda device: {
        "selected_device": device, "cuda_available": True,
        "gpu_name": "Mock GPU", "allocated_memory_bytes": next(samples),
    })
    job_id = ml_client.post("/api/remaster_ml/jobs", data={"description": "test"}).json()["job_id"]
    job = wait_for_job(ml_client, job_id)
    assert job["status"] == "complete"
    assert job["result"]["metadata"]["gpu_diagnostics"] == {
        "selected_device": "cuda:0", "cuda_available": True, "gpu_name": "Mock GPU",
        "allocated_memory_before_bytes": 128, "allocated_memory_after_bytes": 256,
    }


@pytest.mark.parametrize("blocked_stage", ["rendering_prompt", "generating", "encoding"])
def test_expensive_worker_stages_do_not_block_polling(ml_client, monkeypatch, tmp_path, minimal_midi_path, blocked_stage):
    entered = threading.Event()
    release = threading.Event()

    def block(stage):
        if stage == blocked_stage:
            entered.set()
            assert release.wait(5)

    class BlockingInference(FakeInference):
        def generate_from_audio(self, prompt_path, output_path, descriptions, duration):
            block("generating")
            return super().generate_from_audio(prompt_path, output_path, descriptions, duration)

    def render(input_path, *args):
        block("rendering_prompt")
        output = input_path.with_suffix(".wav")
        output.write_bytes(b"mock prompt")
        return output

    def convert(source, destination):
        block("encoding")
        destination.write_bytes(b"mock mp3")

    soundfont = tmp_path / "snes.sf2"
    soundfont.touch()
    monkeypatch.setattr(api_ml, "get_soundfont_path", lambda style: soundfont)
    monkeypatch.setattr(api_ml, "get_inference_engine", lambda *args, **kwargs: BlockingInference())
    monkeypatch.setattr(api_ml, "render_midi_to_audio", render)
    monkeypatch.setattr(audio_renderer, "convert_to_mp3", convert)
    response = ml_client.post(
        "/api/remaster_ml/jobs", data={"description": "test", "prompt_mode": "audio"},
        files={"file": ("input.mid", minimal_midi_path.read_bytes(), "audio/midi")},
    )
    job_id = response.json()["job_id"]
    try:
        assert entered.wait(5)
        assert ml_client.get(f"/api/remaster_ml/jobs/{job_id}").json()["stage"] == blocked_stage
    finally:
        release.set()
    assert wait_for_job(ml_client, job_id)["status"] == "complete"