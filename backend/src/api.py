"""FastAPI backend for MIDI remastering."""

import asyncio
import json
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the backend directory (no-op if file absent)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import mido
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from src.audio_renderer import check_dependencies, get_tool_versions, render_midi_to_audio
from src.instrument_mapper import get_channel_classifications, remap_midi
from src.midi_edits import apply_channel_overrides, build_editor_analysis, parse_channel_overrides
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

@asynccontextmanager
async def _lifespan(app):
    """Application lifespan: start background cleanup task, cancel it on shutdown."""
    task = asyncio.create_task(cleanup_old_files())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="MIDI Remastering API", version="0.4.0", lifespan=_lifespan)


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


# Startup is handled by the lifespan context manager above.


def create_workspace() -> Path:
    workspace = TEMP_DIR / uuid.uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _normalize_soundfont_id(value: str | None, default: str = "snes") -> str:
    soundfont = (value or "").strip().lower()
    return soundfont if soundfont in VALID_IDS else default


def _normalize_source_style(value: str | None) -> str | None:
    source_style = (value or "").strip().lower() or None
    if source_style not in VALID_IDS:
        return None
    return source_style


async def _parse_uploaded_midi(file: UploadFile, workspace: Path) -> tuple[str, Path, mido.MidiFile]:
    input_basename = safe_midi_input_basename(file.filename or "input.mid")
    input_path = workspace / input_basename
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
    return input_basename, input_path, midi


def _get_workspace(request_id: str) -> Path:
    if not is_safe_request_id(request_id):
        raise HTTPException(400, detail=error_body("Invalid request_id.", code="INVALID_REQUEST_ID"))
    workspace = TEMP_DIR / request_id
    if not workspace.exists() or not workspace.is_dir():
        raise HTTPException(404, detail=error_body("Workspace not found or expired.", code="WORKSPACE_NOT_FOUND"))
    return workspace


def _get_workspace_metadata(workspace: Path) -> dict:
    metadata_path = workspace / "metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_workspace_input_path(workspace: Path) -> Path:
    metadata = _get_workspace_metadata(workspace)
    input_filename = metadata.get("input_filename")
    if isinstance(input_filename, str):
        candidate = workspace / safe_midi_input_basename(input_filename)
        if candidate.exists():
            return candidate

    candidates = sorted(
        p for p in workspace.glob("*.mid*")
        if not p.name.upper().startswith(("SNESREMAP_", "GBAREMAP_", "NDSREMAP_", "PS2REMAP_", "WIIREMAP_", "ML_"))
    )
    if candidates:
        return candidates[0]
    raise HTTPException(404, detail=error_body("Original MIDI not found in workspace.", code="INPUT_MIDI_NOT_FOUND"))


def _schedule_cleanup(workspace: Path):
    async def delayed_cleanup():
        await asyncio.sleep(1800)
        shutil.rmtree(workspace, ignore_errors=True)

    asyncio.create_task(delayed_cleanup())


@app.post("/api/remaster/analyze")
async def analyze_remaster(
    file: UploadFile = File(...),
    soundfont: str = Form("snes"),
    source_style: str | None = Form(None),
):
    soundfont = _normalize_soundfont_id(soundfont)
    source_style = _normalize_source_style(source_style)

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
    try:
        input_basename, _input_path, midi = await _parse_uploaded_midi(file, workspace)
        processing_logs = [
            log_event("info", "upload", "File received and saved"),
            log_event("info", "analyze", "MIDI analyzed for advanced editing"),
        ]
        analysis = build_editor_analysis(midi, soundfont, source_style=source_style)
        provenance = {
            "input_filename": input_basename,
            "mode": "analysis",
            "style": soundfont,
            "source_style": source_style,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "tool_versions": get_tool_versions(),
        }
        (workspace / "metadata.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        _schedule_cleanup(workspace)
        return {
            "request_id": workspace.name,
            "soundfont": soundfont,
            "source_style": source_style,
            "input_filename": input_basename,
            "channels": analysis["channels"],
            "available_programs": analysis["available_programs"],
            "preserve_compatible_programs": analysis["preserve_compatible_programs"],
            "logs": processing_logs,
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
                "Analysis error. Check logs or try again.",
                code="ANALYSIS_ERROR",
                debug=str(e),
            ),
        )


@app.get("/api/soundfonts")
async def list_soundfonts():
    options = list_soundfonts_options()
    return options


@app.post("/api/remaster")
async def remaster(
    file: UploadFile | None = File(None),
    soundfont: str = Form("snes"),
    source_style: str | None = Form(None),
    request_id: str | None = Form(None),
    channel_overrides: str | None = Form(None),
):
    soundfont = _normalize_soundfont_id(soundfont)
    source_style = _normalize_source_style(source_style)
    preserve_compatible_programs = source_style == soundfont

    if file is None and not request_id:
        raise HTTPException(
            400,
            detail=error_body("Provide a MIDI file or a request_id from analysis.", code="MISSING_INPUT"),
        )

    if file is not None and not is_allowed_extension(file.filename or ""):
        raise HTTPException(
            400,
            detail=error_body(
                f"Only {', '.join(('.mid', '.midi'))} files accepted",
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
    workspace = create_workspace() if file is not None else _get_workspace(request_id or "")

    try:
        if file is not None:
            input_basename, input_path, midi = await _parse_uploaded_midi(file, workspace)
            processing_logs = [log_event("info", "upload", "File received and saved")]
        else:
            input_path = _get_workspace_input_path(workspace)
            input_basename = input_path.name
            midi = await asyncio.wait_for(asyncio.to_thread(mido.MidiFile, input_path), timeout=30.0)
            processing_logs = [log_event("info", "upload", "Using analyzed MIDI workspace")]

        overrides = parse_channel_overrides(channel_overrides)
        if overrides:
            midi = apply_channel_overrides(midi, overrides)
            processing_logs.append(log_event("info", "edit", f"Applied advanced edits to {len(overrides)} channel(s)"))

        classifications = get_channel_classifications(
            midi,
            soundfont_id=soundfont,
            preserve_compatible_programs=preserve_compatible_programs,
        )
        processing_logs.append(log_event("info", "classify", "Channels classified"))

        output_midi = remap_midi(
            midi,
            soundfont_id=soundfont,
            preserve_compatible_programs=preserve_compatible_programs,
        )
        stem = Path(input_basename).stem
        safe_stem = "".join(c for c in stem if c.isalnum() or c in "-_")
        safe_stem = safe_stem[:200] or "song"
        output_filename = f"{soundfont.upper()}remap_{safe_stem}.mid"
        output_path = workspace / output_filename
        output_midi.save(str(output_path))
        processing_logs.append(log_event("info", "render", "MIDI remapped to soundfont"))

        soundfont_path = get_soundfont_path(soundfont)
        audio_url = None
        audio_error = None
        if soundfont_path.exists():
            try:
                # Rely on subprocess-level timeouts inside render_midi_to_audio
                # (FluidSynth: 120 s, LAME: 90 s) rather than asyncio.wait_for.
                # On Python 3.12+, wait_for + to_thread hangs until the thread
                # exits regardless of the timeout, making it ineffective here.
                audio_path = await asyncio.to_thread(
                    render_midi_to_audio,
                    output_path,
                    soundfont_path,
                    "mp3",
                    False,
                    0.35,
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

        _schedule_cleanup(workspace)

        tool_versions = get_tool_versions()
        previous_metadata = _get_workspace_metadata(workspace)
        provenance = {
            "input_filename": input_basename,
            "mode": "baseline",
            "style": soundfont,
            "source_style": source_style,
            "preserve_compatible_programs": preserve_compatible_programs,
            "source_request_id": request_id,
            "applied_overrides": {str(k): v for k, v in overrides.items()},
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "tool_versions": tool_versions,
        }
        metadata_path = workspace / "metadata.json"
        metadata_path.write_text(json.dumps({**previous_metadata, **provenance}, indent=2), encoding="utf-8")

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
        if file is not None:
            shutil.rmtree(workspace, ignore_errors=True)
        raise
    except Exception as e:
        if file is not None:
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

