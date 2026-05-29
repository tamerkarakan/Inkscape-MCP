"""
Error hierarchy for Inkscape MCP server.
All domain errors carry structured information for MCP isError responses.
"""
from __future__ import annotations

import re
from typing import ClassVar


class InkscapeError(Exception):
    """Base for all Inkscape MCP domain errors.

    These become MCP ``isError: true`` responses, not JSON-RPC protocol errors.
    """

    code: str = "INKSCAPE_ERROR"
    message: str = "An Inkscape error occurred"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        self.detail = message or self.message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.detail}


class InkscapeNotFoundError(InkscapeError):
    """inkscape.com binary not found at configured path."""
    code = "INKSCAPE_NOT_FOUND"


class InkscapeProcessError(InkscapeError):
    """Subprocess failed to start or died unexpectedly."""
    code = "INKSCAPE_PROCESS_ERROR"


class InkscapeTimeoutError(InkscapeError):
    """A subprocess command timed out."""
    code = "INKSCAPE_TIMEOUT"


class InkscapeActionError(InkscapeError):
    """Invalid action name or argument."""
    code = "INKSCAPE_ACTION_FAILED"

    def __init__(self, action: str, stderr: str = "") -> None:
        msg = f"Action '{action}' failed"
        if stderr.strip():
            msg = f"{msg}: {stderr.strip()}"
        super().__init__(msg)
        self.action = action
        self.stderr = stderr


class InkscapeExportError(InkscapeError):
    """Export failed (file unwritable, format unsupported, etc.)."""
    code = "INKSCAPE_EXPORT_FAILED"


class InkscapeFileError(InkscapeError):
    """File could not be opened or read."""
    code = "INKSCAPE_FILE_ERROR"


class InkscapeSecurityError(InkscapeError):
    """Security check failed (path traversal, forbidden directory, etc.)."""
    code = "INKSCAPE_SECURITY_ERROR"


# ── Domain logic errors (not Inkscape process errors) ──


class DocumentNotFoundError(InkscapeError):
    """The requested document does not exist."""
    code = "DOCUMENT_NOT_FOUND"


class StaleRevisionError(InkscapeError):
    """Expected revision does not match current revision."""
    code = "STALE_REVISION"

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"Stale revision: expected {expected}, actual {actual}")
        self.expected = expected
        self.actual = actual


class IdNotFoundError(InkscapeError):
    """Object ID does not exist (distinct from stale revision)."""
    code = "ID_NOT_FOUND"

    def __init__(self, object_id: str) -> None:
        super().__init__(f"Object id '{object_id}' not found")
        self.object_id = object_id


class IdDestroyedError(InkscapeError):
    """Object ID was destroyed by a prior id-changing operation."""
    code = "ID_DESTROYED"

    def __init__(self, object_id: str, operation: str = "") -> None:
        msg = f"Object id '{object_id}' was destroyed"
        if operation:
            msg += f" by '{operation}'"
        super().__init__(msg)
        self.object_id = object_id


class DestructiveOpBlockedError(InkscapeError):
    """Destructive operation blocked by server policy."""
    code = "DESTRUCTIVE_OP_BLOCKED"

    def __init__(self, tool_name: str) -> None:
        super().__init__(
            f"Destructive operation '{tool_name}' requires confirmation. "
            "Set require_confirmation_for_destructive=false or use elicitation."
        )
        self.tool_name = tool_name


# ── Stderr parser ──

_STDERR_PATTERNS: ClassVar[list[tuple[str, type[InkscapeError]]]] = [
    (r"could not find action for: (\S+)", InkscapeActionError),
    (r"cannot be opened!", InkscapeFileError),
    (r"doesn't exist", InkscapeFileError),
    (r"failed to create document", InkscapeFileError),
    (r"failed to open", InkscapeFileError),
    (r"Not in gui mode!", InkscapeActionError),
    (r"No such file or directory", InkscapeFileError),
]


def parse_stderr(stderr: str) -> InkscapeError | None:
    """Scan Inkscape stderr for known error patterns.

    Returns a typed domain error if a pattern matches, otherwise None.
    Exit code 0 from Inkscape is NOT reliable; always parse stderr.
    """
    if not stderr or not stderr.strip():
        return None

    # Try exact patterns first
    for pattern, error_cls in _STDERR_PATTERNS:
        m = re.search(pattern, stderr, re.IGNORECASE)
        if m:
            if error_cls is InkscapeActionError:
                return error_cls(m.group(1), stderr)
            return error_cls(stderr.strip())

    # Generic warning text → generic error
    warning_lines = [ln for ln in stderr.splitlines() if "WARNING" in ln or "ERROR" in ln]
    if warning_lines:
        return InkscapeError(warning_lines[0].strip())

    return None
