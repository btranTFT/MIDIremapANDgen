"""ML-based audio generation endpoint using MusicGen."""

import asyncio
import json
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

import mido
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.audio_renderer import get_tool_versions, render_midi_to_audio
from src.log_events import log_event
from src.ml_inference import (
    check_ml_dependencies,
    get_checkpoint_path,
    get_device_diagnostics,
    get_inference_engine,
    get_ml_diagnostics,
    release_cuda_cache,
)
from src.schema import (
    error_body,
    is_allowed_content_type,
    is_allowed_extension,
    MAX_UPLOAD_BYTES,
    safe_midi_input_basename,
)
from src.soundfonts import get_soundfont_path

router = APIRouter()
_GENERATION_TIMEOUT_SECONDS = 1800.0
_generation_lock = asyncio.Lock()
_jobs: dict[str, dict] = {}
_job_tasks: set[asyncio.Task] = set()


def _set_stage(job: dict | None, stage: str, progress: int, message: str):
    if job is not None:
        job.update(stage=stage, progress=progress, message=message)


def _safe_midi_duration_seconds(midi_path: Path, fallback_seconds: float = 8.0) -> float:
    """Return MIDI duration in seconds, falling back to a sane default on parse issues."""
    try:
        midi = mido.MidiFile(str(midi_path))
        duration = float(getattr(midi, "length", 0.0) or 0.0)
        if duration > 0.0:
            return duration
    except Exception:
        pass
    return fallback_seconds


def get_ml_availability() -> bool:
    """Return True when AudioCraft is installed; checkpoints are optional."""
    diagnostics = get_ml_diagnostics()
    return bool(diagnostics["ml_available"])


def get_ml_available_styles() -> list:
    """Return styles available to ML, including base-model styles."""
    deps = check_ml_dependencies()
    if not deps.get("audiocraft"):
        return []
    return ["snes", "gba", "nds", "ps2", "wii"]


@router.get("/ml/health")
async def ml_health():
    """Check ML dependencies and optional style checkpoints."""
    diagnostics = get_ml_diagnostics()
    status = "ready" if get_ml_availability() else "unavailable"
    return {"status": status, "details": diagnostics}


@router.get("/ml/available_soundfonts")
async def ml_available_soundfonts():
    """Get list of soundfonts with available ML models."""
    deps = check_ml_dependencies()
    return {
        "available": deps.get("available_soundfonts", []),
        "audiocraft_installed": deps.get("audiocraft", False),
    }


async def _prepare_ml_request(file, soundfont, description, prompt_mode, duration):
    from src.api import create_workspace
    
    # Validate soundfont
    soundfont = (soundfont or "").strip().lower()
    if soundfont not in ["snes", "gba", "nds", "ps2", "wii"]:
        soundfont = "snes"
    
    # Validate ML dependencies for this specific soundfont
    diagnostics = await asyncio.to_thread(get_ml_diagnostics, soundfont)
    if not diagnostics["ml_available"]:
        raise HTTPException(
            503,
            detail=error_body(
                diagnostics["ml_reason"],
                code="ML_UNAVAILABLE",
                debug=diagnostics["recommended_action"],
            ),
        )
    prompt_mode = (prompt_mode or "text").strip().lower()
    if prompt_mode not in {"text", "audio"}:
        raise HTTPException(400, detail=error_body("prompt_mode must be 'text' or 'audio'.", code="INVALID_PROMPT_MODE"))
    if not description.strip():
        raise HTTPException(400, detail=error_body("A text description is required.", code="MISSING_DESCRIPTION"))
    if duration not in {15, 30}:
        raise HTTPException(400, detail=error_body("duration must be 15 or 30 seconds.", code="INVALID_DURATION"))
    if prompt_mode == "audio" and file is None:
        raise HTTPException(400, detail=error_body("A MIDI file is required for audio prompt mode.", code="MISSING_INPUT"))
    if file is not None and not is_allowed_extension(file.filename or ""):
        raise HTTPException(
            400,
            detail=error_body(
                "Only .mid, .midi files accepted for ML generation",
                code="INVALID_EXTENSION",
            ),
        )
    if file is not None and not is_allowed_content_type(file.content_type):
        raise HTTPException(
            415,
            detail=error_body(
                "Content-Type not allowed for upload. Use audio/midi or application/octet-stream.",
                code="INVALID_CONTENT_TYPE",
            ),
        )

    workspace = create_workspace()
    input_basename = safe_midi_input_basename(file.filename or "input.mid") if file else "text_prompt.mid"
    input_path = workspace / input_basename

    try:
        read_size = 0
        chunk_size = 1024 * 1024
        if file is not None:
            with input_path.open("wb") as output_file:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    read_size += len(chunk)
                    if read_size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            413,
                            detail=error_body(
                                f"File exceeds maximum size ({MAX_UPLOAD_BYTES // (1024*1024)} MiB).",
                                code="PAYLOAD_TOO_LARGE",
                            ),
                        )
                    output_file.write(chunk)
        return workspace, input_basename, soundfont, prompt_mode
    except HTTPException:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(workspace, ignore_errors=True)
        raise HTTPException(
            500,
            detail=error_body("ML generation failed. Check logs or try again.", code="PROCESSING_ERROR", debug=str(exc)),
        )


async def _generate_ml(workspace, input_basename, soundfont, description, prompt_mode, duration, has_file, started_at, prepared_at, job=None):
    from src.api import _schedule_cleanup

    input_path = workspace / input_basename
    try:
        timings = {
            "upload_validation": prepared_at - started_at,
            "queue_wait": time.perf_counter() - prepared_at,
            "model_loading": 0.0,
            "midi_prompt_rendering": 0.0,
            "musicgen_generation": 0.0,
            "audio_encoding": 0.0,
        }
        processing_logs = [
            log_event(
                "info",
                "upload",
                "MIDI file received and saved" if has_file else "Text prompt received",
            )
        ]
        descriptions = [description.strip()]
        stem = Path(input_basename).stem
        safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem).strip("_")[:200] or "song"
        output_filename = f"ML_{soundfont.upper()}_{'text' if prompt_mode == 'text' else safe_stem}.wav"
        output_wav_path = workspace / output_filename

        if prompt_mode == "audio":
            _set_stage(job, "rendering_prompt", 20, "Rendering MIDI conditioning audio")
            stage_started = time.perf_counter()
            soundfont_path = get_soundfont_path(soundfont)
            if not soundfont_path.exists():
                raise HTTPException(503, detail=error_body(f"Soundfont not found: {soundfont_path.name}", code="SOUNDFONT_NOT_FOUND"))
            prompt_wav_path = await asyncio.to_thread(
                render_midi_to_audio,
                input_path,
                soundfont_path,
                "wav",
                False,
                0.35,
                False,
            )
            timings["midi_prompt_rendering"] = time.perf_counter() - stage_started
            processing_logs.append(log_event("info", "render", "MIDI rendered as audio prompt"))

        _set_stage(job, "loading_model", 30, "Waiting for the MusicGen model")
        lock_started = time.perf_counter()
        async with _generation_lock:
            timings["generation_lock_wait"] = time.perf_counter() - lock_started
            stage_started = time.perf_counter()
            inference = await asyncio.to_thread(get_inference_engine, soundfont, conditioning_type=prompt_mode)
            await asyncio.to_thread(inference.load_model)
            timings["model_loading"] = time.perf_counter() - stage_started
            device = str(getattr(inference, "device", "cpu"))
            gpu_before = await asyncio.to_thread(get_device_diagnostics, device)
            _set_stage(job, "generating", 50, "Generating audio with MusicGen")
            stage_started = time.perf_counter()
            if prompt_mode == "audio":
                generation = asyncio.create_task(asyncio.to_thread(
                    inference.generate_from_audio, prompt_wav_path, output_wav_path, descriptions, duration
                ))
            else:
                generation = asyncio.create_task(asyncio.to_thread(
                    inference.generate_from_text, output_wav_path, descriptions, duration
                ))
            try:
                generated_path = await asyncio.wait_for(
                    asyncio.shield(generation), timeout=_GENERATION_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                try:
                    await generation
                except Exception:
                    pass
                await asyncio.to_thread(release_cuda_cache, device)
                raise HTTPException(
                    500,
                    detail=error_body(
                        "ML generation timed out after 30 minutes. Try a shorter MIDI file or check GPU availability.",
                        code="ML_GENERATION_TIMEOUT",
                    ),
                )
            except Exception:
                await asyncio.to_thread(release_cuda_cache, device)
                raise
            timings["musicgen_generation"] = time.perf_counter() - stage_started
            gpu_after = await asyncio.to_thread(get_device_diagnostics, device)
        processing_logs.append(log_event("info", "encode", "MusicGen audio generated"))

        _set_stage(job, "encoding", 85, "Encoding generated audio")
        stage_started = time.perf_counter()
        from src.audio_renderer import convert_to_mp3
        output_mp3_path = generated_path.with_suffix(".mp3")
        await asyncio.to_thread(convert_to_mp3, generated_path, output_mp3_path)
        timings["audio_encoding"] = time.perf_counter() - stage_started
        processing_logs.append(log_event("info", "encode", "Converted to MP3"))

        checkpoint_path = get_checkpoint_path(soundfont)
        tool_versions = await asyncio.to_thread(get_tool_versions)
        timings["total_job"] = time.perf_counter() - started_at
        provenance = {
            "input_filename": input_basename,
            "mode": "ml",
            "style": soundfont,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "tool_versions": tool_versions,
            "checkpoint": checkpoint_path.name if checkpoint_path else None,
            "fallback_to_base": checkpoint_path is None,
            "model_name": inference.model_name,
            "checkpoint_loaded": inference.checkpoint_loaded,
            "timings_seconds": timings,
            "gpu_diagnostics": {
                "selected_device": gpu_before["selected_device"],
                "cuda_available": gpu_before["cuda_available"],
                "gpu_name": gpu_before["gpu_name"],
                "allocated_memory_before_bytes": gpu_before["allocated_memory_bytes"],
                "allocated_memory_after_bytes": gpu_after["allocated_memory_bytes"],
            },
        }
        metadata_path = workspace / "metadata.json"
        metadata_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        _schedule_cleanup(workspace)

        return {
            "request_id": workspace.name,
            "audio_url": f"/download/audio/{workspace.name}/{output_mp3_path.name}",
            "prompt_soundfont": soundfont,
            "description": descriptions[0],
            "prompt_mode": prompt_mode,
            "duration_seconds": duration,
            "visualization": None,
            "method": "musicgen_ml",
            "logs": processing_logs,
            "metadata_url": f"/download/metadata/{workspace.name}",
            "metadata": provenance,
        }

    except HTTPException:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(workspace, ignore_errors=True)
        raise HTTPException(
            500,
            detail=error_body(
                "ML generation failed. Check logs or try again.",
                code="PROCESSING_ERROR",
                debug=str(e),
            ),
        )


async def _run_job(job, workspace, input_basename, soundfont, description, prompt_mode, duration, has_file, started_at, prepared_at):
    job.update(status="running")
    try:
        result = await _generate_ml(
            workspace, input_basename, soundfont, description, prompt_mode, duration, has_file, started_at, prepared_at, job
        )
        job.update(status="complete", stage="complete", progress=100, message="Generation complete", result=result)
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else error_body(
            "ML generation failed. Check logs or try again.", code="PROCESSING_ERROR", debug=str(exc)
        )
        job.update(status="failed", message="Generation failed", error=detail)
    finally:
        asyncio.get_running_loop().call_later(1800, _jobs.pop, job["job_id"], None)


@router.post("/remaster_ml")
async def remaster_ml(
    file: UploadFile | None = File(None),
    soundfont: str = Form("snes"),
    description: str = Form(""),
    prompt_mode: str = Form("text"),
    duration: int = Form(15),
):
    """Generate audio using MusicGen from text or an optional MIDI audio prompt."""
    started_at = time.perf_counter()
    workspace, input_basename, soundfont, prompt_mode = await _prepare_ml_request(
        file, soundfont, description, prompt_mode, duration
    )
    prepared_at = time.perf_counter()
    return await _generate_ml(workspace, input_basename, soundfont, description, prompt_mode, duration, file is not None, started_at, prepared_at)


@router.post("/remaster_ml/jobs", status_code=202)
async def submit_ml_job(
    file: UploadFile | None = File(None),
    soundfont: str = Form("snes"),
    description: str = Form(""),
    prompt_mode: str = Form("text"),
    duration: int = Form(15),
):
    started_at = time.perf_counter()
    workspace, input_basename, soundfont, prompt_mode = await _prepare_ml_request(
        file, soundfont, description, prompt_mode, duration
    )
    prepared_at = time.perf_counter()
    job_id = uuid.uuid4().hex
    job = {"job_id": job_id, "status": "queued", "stage": "validating", "progress": 0,
           "message": "Queued for generation", "error": None, "result": None}
    _jobs[job_id] = job
    task = asyncio.create_task(_run_job(
        job, workspace, input_basename, soundfont, description, prompt_mode, duration, file is not None, started_at, prepared_at
    ))
    _job_tasks.add(task)
    task.add_done_callback(_job_tasks.discard)
    return dict(job)


@router.get("/remaster_ml/jobs/{job_id}")
async def get_ml_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail=error_body("ML job not found or expired.", code="JOB_NOT_FOUND"))
    return dict(job)
