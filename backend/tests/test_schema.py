"""Minimal tests for schema validation logic (no new dependencies)."""

import unittest
import sys
from pathlib import Path

# Allow importing src when run from repo root or backend
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from src.schema import (
    ALLOWED_MIDI_EXTENSIONS,
    ALLOWED_UPLOAD_CONTENT_TYPES,
    error_body,
    is_allowed_content_type,
    is_allowed_extension,
    is_safe_download_filename,
    is_safe_request_id,
    safe_midi_input_basename,
    sanitize_basename,
)


class TestErrorBody(unittest.TestCase):
    def test_error_body_message_only(self):
        out = error_body("Something failed")
        self.assertEqual(out, {"detail": "Something failed"})

    def test_error_body_with_code(self):
        out = error_body("Invalid extension", code="INVALID_EXTENSION")
        self.assertEqual(out["detail"], "Invalid extension")
        self.assertEqual(out["code"], "INVALID_EXTENSION")


class TestExtensionAllowlist(unittest.TestCase):
    def test_allowed_extensions(self):
        for ext in (".mid", ".midi", ".MID", ".MIDI"):
            self.assertTrue(is_allowed_extension(f"file{ext}"))
        self.assertFalse(is_allowed_extension("file.txt"))
        self.assertFalse(is_allowed_extension("file"))
        self.assertFalse(is_allowed_extension("file.mid.exe"))


class TestContentTypeAllowlist(unittest.TestCase):
    def test_allowed_types(self):
        self.assertTrue(is_allowed_content_type("audio/midi"))
        self.assertTrue(is_allowed_content_type("application/octet-stream"))
        self.assertTrue(is_allowed_content_type("audio/x-midi"))
        self.assertTrue(is_allowed_content_type("audio/midi; charset=utf-8"))
        self.assertTrue(is_allowed_content_type(None))

    def test_rejected_types(self):
        self.assertFalse(is_allowed_content_type("text/plain"))
        self.assertFalse(is_allowed_content_type("application/x-www-form-urlencoded"))


class TestSanitizeBasename(unittest.TestCase):
    def test_empty_or_whitespace(self):
        self.assertEqual(sanitize_basename(""), "input")
        self.assertEqual(sanitize_basename("   "), "input")

    def test_strips_path_components(self):
        self.assertNotIn("/", sanitize_basename("a/b/c.mid"))
        self.assertNotIn("\\", sanitize_basename("a\\b\\c.mid"))

    def test_safe_chars_only(self):
        self.assertEqual(sanitize_basename("normal.mid"), "normal.mid")
        out = sanitize_basename("x" * 300)
        self.assertLessEqual(len(out), 200)


class TestSafeMidiInputBasename(unittest.TestCase):
    def test_force_midi_extension(self):
        self.assertTrue(safe_midi_input_basename("x").endswith(".mid"))
        self.assertTrue(safe_midi_input_basename("a.MID").endswith(".mid"))
        self.assertTrue(safe_midi_input_basename("b.midi").endswith(".midi"))

    def test_no_path_traversal(self):
        out = safe_midi_input_basename("../../../etc/passwd")
        self.assertNotIn("..", out)
        self.assertNotIn("/", out)


class TestSafeRequestId(unittest.TestCase):
    def test_valid_32_hex(self):
        self.assertTrue(is_safe_request_id("a" * 32))
        self.assertTrue(is_safe_request_id("0123456789abcdef" * 2))

    def test_invalid(self):
        self.assertFalse(is_safe_request_id(""))
        self.assertFalse(is_safe_request_id("short"))
        self.assertFalse(is_safe_request_id("g" * 32))
        self.assertFalse(is_safe_request_id("../abc"))


class TestSafeDownloadFilename(unittest.TestCase):
    def test_safe_names(self):
        self.assertTrue(is_safe_download_filename("SNESremapsong.mid"))
        self.assertTrue(is_safe_download_filename("ML_SNES_track.mp3"))

    def test_rejects_path_traversal(self):
        self.assertFalse(is_safe_download_filename("../../../etc/passwd"))
        self.assertFalse(is_safe_download_filename("a/b"))
        self.assertFalse(is_safe_download_filename("..\\file.mid"))

    def test_rejects_empty(self):
        self.assertFalse(is_safe_download_filename(""))


if __name__ == "__main__":
    unittest.main()
