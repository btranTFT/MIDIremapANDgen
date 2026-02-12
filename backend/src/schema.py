"""Shared validation and error response schema for the API."""

import re
from pathlib import Path

# Allowlist: only these extensions and content-types for uploads
ALLOWED_MIDI_EXTENSIONS = (".mid", ".midi")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MiB
ALLOWED_UPLOAD_CONTENT_TYPES = frozenset(
    {"audio/midi", "application/octet-stream", "audio/x-midi"}
)
# request_id is workspace name: 32-char hex (uuid4.hex)
REQUEST_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
# Download filename: our generated names (alphanumeric, dot, hyphen, underscore)
SAFE_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


def error_body(
    message: str,
    code: str | None = None,
    debug: str | None = None,
    headline: str | None = None,
    next_step: str | None = None,
) -> dict:
    """Build consistent error JSON: { detail, code?, debug?, headline?, next_step? }. All except detail are optional."""
    body: dict = {"detail": message}
    if code:
        body["code"] = code
    if debug:
        body["debug"] = debug
    if headline:
        body["headline"] = headline
    if next_step:
        body["next_step"] = next_step
    return body


def sanitize_basename(name: str) -> str:
    """
    Return a safe basename for writing under a workspace.
    No path components (no / or \), no empty, no leading dot that could hide.
    """
    if not name or not name.strip():
        return "input"
    p = Path(name.strip())
    base = p.name
    # Remove any path components that might have slipped
    base = base.split("/")[-1].split("\\")[-1]
    # Allow only safe chars; truncate length
    safe = "".join(c for c in base if c.isalnum() or c in " ._-")[:200]
    return safe.strip() or "input"


def safe_midi_input_basename(original: str) -> str:
    """
    From original filename, produce a safe basename that ends with .mid or .midi (lowercase).
    Used for writing uploaded content; extension is forced to allowlist.
    """
    base = sanitize_basename(original)
    lower = base.lower()
    idx_midi = lower.rfind(".midi")
    if idx_midi >= 0:
        stem = base[:idx_midi].rstrip() or "input"
        return stem + ".midi"
    idx_mid = lower.rfind(".mid")
    if idx_mid >= 0:
        stem = base[:idx_mid].rstrip() or "input"
        return stem + ".mid"
    return base + ".mid"


def is_safe_request_id(value: str) -> bool:
    """True if value is a valid workspace id (32 hex chars)."""
    return bool(value and REQUEST_ID_PATTERN.fullmatch(value))


def is_safe_download_filename(value: str) -> bool:
    """True if filename has no path traversal and only safe chars."""
    if not value or "/" in value or "\\" in value or ".." in value:
        return False
    return bool(SAFE_FILENAME_PATTERN.fullmatch(value.strip()))


def is_allowed_extension(filename: str) -> bool:
    """True if filename ends with an allowed MIDI extension."""
    fn = (filename or "").strip().lower()
    return any(fn.endswith(ext) for ext in ALLOWED_MIDI_EXTENSIONS)


def is_allowed_content_type(content_type: str | None) -> bool:
    """True if Content-Type is allowed for MIDI upload (or missing/any)."""
    if not content_type:
        return True
    # Allow "audio/midi; charset=..." etc.
    main = content_type.split(";")[0].strip().lower()
    return main in ALLOWED_UPLOAD_CONTENT_TYPES
