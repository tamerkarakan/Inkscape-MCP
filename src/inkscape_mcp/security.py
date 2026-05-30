"""
Security: path sandbox, action allowlist, argument validation.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from .exceptions import InkscapeSecurityError

# Action-name regex: alphanumeric + dots, hyphens, underscores (as in core-actions.txt)
_ACTION_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9._\-:]*$")
# Argument regex for safe action args (no shell/action-chain metacharacters)
# ; and : are banned — they would allow action-chain injection (Madde 8)
_ACTION_ARG_RE = re.compile(r"^[a-zA-Z0-9._,=/\- +%#]*$")


@dataclass
class SecurityConfig:
    """Server-wide security configuration."""

    # Filesystem
    workspace_root: Path
    deny_path_traversal: bool = True

    # Size limits
    max_svg_size_bytes: int = 52_428_800  # 50 MB
    max_export_size_bytes: int = 104_857_600  # 100 MB

    # Timeouts (seconds)
    default_timeout: int = 30
    export_timeout: int = 60
    trace_timeout: int = 120

    # Formats
    allowed_export_formats: tuple[str, ...] = (
        "svg", "png", "pdf", "ps", "eps", "emf", "wmf", "xaml"
    )

    # Sessions
    max_concurrent_sessions: int = 5
    session_ttl_seconds: int = 3600  # 1 hour

    # Destructive operations
    require_confirmation_for_destructive: bool = True

    # Preview
    max_preview_bytes: int = 2_097_152  # 2 MB — larger → resource_link


# ── Path sandbox ──


def validate_path(path: Path, config: SecurityConfig) -> Path:
    """Validate that *path* is within workspace_root and safe.

    Returns the resolved real path, or raises InkscapeSecurityError.
    Error messages use sanitized paths — no FS absolute-path leak.
    """
    workspace = config.workspace_root.resolve(strict=False)

    try:
        resolved = path.resolve(strict=False)
    except (OSError, ValueError) as exc:
        raise InkscapeSecurityError("Invalid path") from exc

    # Check path is under workspace
    try:
        resolved.relative_to(workspace)
    except ValueError:
        raise InkscapeSecurityError(
            "Path is outside the allowed workspace"
        )

    # Symlink/traversal check: real path must stay under workspace
    if resolved.exists() or resolved.parent.exists():
        try:
            real = resolved.resolve(strict=False)
            real.relative_to(workspace)
        except (ValueError, OSError):
            raise InkscapeSecurityError(
                "Path resolves outside workspace"
            )

    return resolved


def validate_path_traversal(path_str: str) -> None:
    """Reject paths that contain '..' segments."""
    normalized = os.path.normpath(path_str)
    if ".." in normalized.split(os.sep):
        raise InkscapeSecurityError(
            f"Path traversal detected: '{path_str}' contains '..'"
        )


def validate_svg_size(svg_bytes: bytes, config: SecurityConfig) -> None:
    """Reject SVG content exceeding max size."""
    if len(svg_bytes) > config.max_svg_size_bytes:
        raise InkscapeSecurityError(
            f"SVG content too large: {len(svg_bytes)} bytes "
            f"(max {config.max_svg_size_bytes})"
        )


# ── Action allowlist ──


def load_action_list(path: Path) -> set[str]:
    """Parse an action-list dump (name : description) into a set of action names."""
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split(":", 1)[0].strip()
        if name:
            names.add(name)
    return names


def validate_action_name(name: str) -> None:
    """Validate action name format (safety check)."""
    if not _ACTION_NAME_RE.match(name):
        raise InkscapeSecurityError(f"Invalid action name format: '{name}'")


def validate_action_arg(arg: str | None) -> None:
    """Validate action argument format (no shell metacharacters)."""
    if arg is not None and not _ACTION_ARG_RE.match(arg):
        raise InkscapeSecurityError(
            f"Invalid action argument format: '{arg}'"
        )


# ── Action allowlist (built from reference/action-list-full.txt) ──

# GUI actions that require display — always rejected in headless
_GUI_ACTIONS: set[str] = {
    "window-open", "window-close", "window-crash",
    "window-query-geometry", "window-set-geometry",
    "active-window-start", "active-window-end",
    "file-open-window",
}

# Subset of headless-safe actions for run_actions escape hatch
_CORE_ALLOWLIST: ClassVar[set[str]] = {
    # Selection
    "select-by-id", "select-all", "select-clear", "select-invert",
    "select-by-element", "select-list",
    "unselect-by-id",
    # Query
    "query-all", "query-x", "query-y", "query-width", "query-height",
    # Mutation — set attribute/property
    "object-set-attribute", "object-set-property",
    # Path operations
    "object-to-path", "object-stroke-to-path",
    "path-union", "path-difference", "path-intersection", "path-exclusion",
    "path-division", "path-cut", "path-combine", "path-break-apart",
    "path-simplify", "path-flatten", "path-fracture", "path-split",
    # Transform
    "transform-translate", "transform-scale",
    "transform-rotate", "transform-rotate-step",
    "transform-grow", "transform-grow-step",
    "transform-remove", "transform-reapply",
    "object-flip-horizontal", "object-flip-vertical",
    "object-rotate-90-cw", "object-rotate-90-ccw",
    # Delete / duplicate
    "delete", "delete-selection", "duplicate",
    # Stack order
    "selection-top", "selection-bottom",
    "selection-raise", "selection-lower",
    "selection-stack-up", "selection-stack-down",
    # Group / ungroup
    "selection-group", "selection-ungroup", "selection-ungroup-pop",
    # Clip / mask
    "object-set-clip", "object-release-clip",
    "object-set-mask", "object-release-mask",
    # Clone
    "clone", "clone-unlink", "clone-link",
    # Export chain
    "export-filename", "export-type", "export-do",
    "export-dpi", "export-width", "export-height",
    "export-area", "export-area-page", "export-area-drawing",
    "export-background", "export-background-opacity",
    "export-plain-svg", "export-text-to-path",
    "export-overwrite", "export-id", "export-id-only",
    # File
    "file-open", "file-close", "file-new",
    # Misc
    "vacuum-defs", "fit-canvas-to-selection",
    "object-release-clip", "object-release-mask",
    "swap-fill-and-stroke",
    "edit-remove-filter",
}


def is_headless_safe(action_name: str) -> bool:
    """Check if an action is known to work headless."""
    return action_name in _CORE_ALLOWLIST and action_name not in _GUI_ACTIONS


def is_gui_action(action_name: str) -> bool:
    """Check if an action requires a GUI (display)."""
    return action_name in _GUI_ACTIONS
