"""FastAPI backend for MIDI remastering."""

import asyncio
import json
import os
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import mido
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from src.audio_renderer import check_dependencies, get_tool_versions, render_midi_to_audio
from src.instrument_mapper import get_channel_classifications, remap_midi
from src.schema import (
    error_body,
    is_allowed_content_type,
    is_allowed_extension,
    is_safe_download_filename,
    is_safe_request_id,
    MAX_UPLOAD_BYTES,
    safe_midi_input_basename,
)
from src.log_events import log_event
from src.soundfonts import VALID_IDS, get_soundfont_path, list_soundfonts as list_soundfonts_options

app = FastAPI(title="MIDI Remastering API", version="0.4.0")


async def _http_exception_handler(request, exc: HTTPException):
    """Return consistent error JSON: { detail, code? }. Backward-compatible when detail is str."""
    if isinstance(exc.detail, dict) and "detail" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)})


app.add_exception_handler(HTTPException, _http_exception_handler)

# Mount ML router
_ml_available_fn = lambda: False
_ml_available_styles_fn = lambda: []
try:
    from src.api_ml import router as ml_router, get_ml_availability, get_ml_available_styles
    app.include_router(ml_router, prefix="/api", tags=["ML Generation"])
    _ml_available_fn = get_ml_availability
    _ml_available_styles_fn = get_ml_available_styles
    print("[API] ML router mounted at /api/remaster_ml")
except ImportError as e:
    print(f"[API] ML router not available: {e}")

# Capabilities: single source for frontend (health); must match schema.MAX_UPLOAD_BYTES
DEFAULT_MAX_UPLOAD_BYTES = MAX_UPLOAD_BYTES

# CORS: Read from env, safe defaults for dev. Production: set CORS_ORIGINS env var.
# Safe default: only localhost (prevents accidental open CORS in production)
_cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
_cors_origins = [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
# Never allow ["*"] with credentials (security risk)
if "*" in _cors_origins:
    _cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    print("[WARN] CORS_ORIGINS contains '*', falling back to localhost only for security")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
TEMP_DIR = BACKEND_ROOT / "temp_uploads"
TEMP_DIR.mkdir(exist_ok=True)


async def cleanup_old_files():
    """Clean up old workspaces: age > 1 hour, or if TEMP_DIR exceeds size limit."""
    MAX_TEMP_SIZE_MB = 500  # Clean aggressively if temp dir exceeds 500 MB
    while True:
        now = datetime.now()
        total_size_mb = 0
        items_to_clean = []
        for item in TEMP_DIR.iterdir():
            if item.is_dir():
                try:
                    age = now - datetime.fromtimestamp(item.stat().st_mtime)
                    # Calculate size
                    size_bytes = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                    size_mb = size_bytes / (1024 * 1024)
                    total_size_mb += size_mb
                    # Mark for cleanup if old OR if we're over limit
                    if age > timedelta(hours=1):
                        items_to_clean.append((item, age))
                except Exception:
                    pass
        # If over limit, clean oldest first
        if total_size_mb > MAX_TEMP_SIZE_MB:
            items_to_clean.sort(key=lambda x: x[1], reverse=True)
            # Clean until we're under 80% of limit
            for item, _ in items_to_clean:
                if total_size_mb <= MAX_TEMP_SIZE_MB * 0.8:
                    break
                try:
                    shutil.rmtree(item, ignore_errors=True)
                    # Recalculate (approximate)
                    total_size_mb *= 0.9  # Rough estimate after deletion
                except Exception:
                    pass
        else:
            # Normal cleanup: age > 1 hour
            for item, _ in items_to_clean:
                try:
                    shutil.rmtree(item, ignore_errors=True)
                except Exception:
                    pass
        await asyncio.sleep(300)


@app.on_event("startup")
async def startup():
    asyncio.create_task(cleanup_old_files())


def create_workspace() -> Path:
    workspace = TEMP_DIR / uuid.uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@app.get("/api/soundfonts")
async def list_soundfonts():
    options = list_soundfonts_options()
    return options


@app.post("/api/remaster")
async def remaster(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    soundfont: str = Form("snes"),
):
    soundfont = (soundfont or "").strip().lower()
    if soundfont not in VALID_IDS:
        soundfont = "snes"

    if not is_allowed_extension(file.filename or ""):
        raise HTTPException(
            400,
            detail=error_body(
                f"Only {', '.join(('.mid', '.midi'))} files accepted",
                code="INVALID_EXTENSION",
            ),
        )
    if not is_allowed_content_type(file.content_type):
        raise HTTPException(
            415,
            detail=error_body(
                "Content-Type not allowed for upload. Use audio/midi or application/octet-stream.",
                code="INVALID_CONTENT_TYPE",
            ),
        )

    workspace = create_workspace()
    input_basename = safe_midi_input_basename(file.filename or "input.mid")
    input_path = workspace / input_basename

    try:
        content = b""
        read_size = 0
        chunk_size = 1024 * 1024
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            read_size += len(chunk)
            if read_size > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    413,
                    detail=error_body(
                        f"File exceeds maximum size ({DEFAULT_MAX_UPLOAD_BYTES // (1024*1024)} MiB).",
                        code="PAYLOAD_TOO_LARGE",
                    ),
                )
            content += chunk
        input_path.write_bytes(content)
        processing_logs = [log_event("info", "upload", "File received and saved")]

        # Parse MIDI with timeout to prevent hangs on corrupt files
        try:
            midi = await asyncio.wait_for(
                asyncio.to_thread(mido.MidiFile, input_path),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                400,
                detail=error_body(
                    "MIDI file parsing timed out. File may be corrupt or too complex.",
                    code="MIDI_PARSE_TIMEOUT",
                ),
            )
        classifications = get_channel_classifications(midi, soundfont_id=soundfont)
        processing_logs.append(log_event("info", "classify", "Channels classified"))

        output_midi = remap_midi(midi, soundfont_id=soundfont)
        stem = Path(input_basename).stem
        safe_stem = "".join(c for c in stem if c.isalnum() or c in " ()-_")
        safe_stem = safe_stem[:200] or "song"
        output_filename = f"{soundfont.upper()}remap{safe_stem}.mid"
        output_path = workspace / output_filename
        output_midi.save(str(output_path))
        processing_logs.append(log_event("info", "render", "MIDI remapped to soundfont"))

        soundfont_path = get_soundfont_path(soundfont)
        audio_url = None
        audio_error = None
        if soundfont_path.exists():
            try:
                audio_path = await asyncio.wait_for(
                    asyncio.to_thread(render_midi_to_audio, output_path, soundfont_path, "mp3"),
                    timeout=240.0,
                )
                audio_url = f"/download/audio/{workspace.name}/{audio_path.name}?sf={soundfont}"
                processing_logs.append(log_event("info", "encode", "Audio rendered to MP3"))
            except Exception as e:
                audio_error = str(e) if str(e) else "Audio rendering failed."
                processing_logs.append(
                    log_event("warn", "encode", "Audio rendering failed", debug=str(e))
                )
        else:
            audio_error = f"Soundfont not found: {soundfont_path.name}"
            processing_logs.append(log_event("warn", "encode", audio_error))

        async def delayed_cleanup():
            await asyncio.sleep(1800)
            shutil.rmtree(workspace, ignore_errors=True)

        background_tasks.add_task(delayed_cleanup)

        tool_versions = get_tool_versions()
        provenance = {
            "input_filename": input_basename,
            "mode": "baseline",
            "style": soundfont,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "tool_versions": tool_versions,
        }
        metadata_path = workspace / "metadata.json"
        metadata_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")

        return {
            "request_id": workspace.name,
            "midi_url": f"/download/midi/{workspace.name}/{output_filename}",
            "audio_url": audio_url,
            "audio_error": audio_error,
            "soundfont": soundfont,
            "classifications": {
                str(ch): {"program": prog, "name": name}
                for ch, (prog, name) in classifications.items()
            },
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
                "Processing error. Check logs or try again.",
                code="PROCESSING_ERROR",
                debug=str(e),
            ),
        )


def _download_path(request_id: str, filename: str) -> Path:
    """Resolve download path; raise HTTPException if invalid or outside TEMP_DIR."""
    if not is_safe_request_id(request_id):
        raise HTTPException(
            400,
            detail=error_body("Invalid request_id.", code="INVALID_REQUEST_ID"),
        )
    if not is_safe_download_filename(filename):
        raise HTTPException(
            400,
            detail=error_body("Invalid filename.", code="INVALID_FILENAME"),
        )
    base = TEMP_DIR.resolve()
    path = (TEMP_DIR / request_id / filename).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        raise HTTPException(
            404,
            detail=error_body("File not found or expired.", code="NOT_FOUND"),
        )
    if not path.exists() or not path.is_file():
        raise HTTPException(
            404,
            detail=error_body("File not found or expired.", code="NOT_FOUND"),
        )
    return path


@app.get("/download/midi/{request_id}/{filename}")
async def download_midi(request_id: str, filename: str):
    path = _download_path(request_id, filename)
    return FileResponse(path, media_type="audio/midi", filename=filename)


@app.get("/download/metadata/{request_id}")
async def download_metadata(request_id: str):
    path = _download_path(request_id, "metadata.json")
    return FileResponse(path, media_type="application/json", filename="metadata.json")


@app.get("/download/audio/{request_id}/{filename}")
async def download_audio(request_id: str, filename: str):
    path = _download_path(request_id, filename)
    return FileResponse(path, media_type="audio/mpeg", filename=filename)


@app.get("/health")
async def health():
    """Single capabilities endpoint: status, deps, ML, styles, max upload size."""
    deps = check_dependencies()
    ml_available = _ml_available_fn()
    available_styles = sorted(VALID_IDS)
    ml_available_styles = _ml_available_styles_fn()
    return {
        "status": "ok",
        "dependencies": deps,
        "ml_available": ml_available,
        "available_styles": available_styles,
        "ml_available_styles": ml_available_styles,
        "max_upload_bytes": DEFAULT_MAX_UPLOAD_BYTES,
    }

