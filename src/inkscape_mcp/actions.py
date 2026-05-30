"""
Action chain builder: constructs safe Inkscape CLI command lists.

IMPORTANT: This module NEVER uses shell=True, string concatenation to build
commands, or invents action names. All action names come from the allowlist.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .exceptions import InkscapeSecurityError
from .security import (
    _ACTION_NAME_RE,
    _ACTION_ARG_RE,
    SecurityConfig,
    is_gui_action,
    is_headless_safe,
    validate_action_arg,
    validate_action_name,
)

# ── Action command builder ──


def build_shell_command(name: str, arg: str | None = None) -> str:
    """Build a single shell-mode command string (for --shell stdin).

    Format: "action_name[:arg]" — one per line.
    """
    validate_action_name(name)
    if arg is not None:
        validate_action_arg(arg)
        return f"{name}:{arg}"
    return name


def build_actions_string(actions: list[tuple[str, str | None]]) -> str:
    """Build a semicolon-separated action chain for --actions mode.

    Each action is (name, arg_or_none).
    """
    parts: list[str] = []
    for name, arg in actions:
        validate_action_name(name)
        if arg is not None:
            validate_action_arg(arg)
            parts.append(f"{name}:{arg}")
        else:
            parts.append(name)
    return ";".join(parts)


def build_actions_file_content(actions: list[tuple[str, str | None]]) -> str:
    """Build actions-file content (semicolon-separated per F12).

    Inkscape --actions-file expects semicolons, NOT newlines.
    """
    return build_actions_string(actions)


# ── Selection replay ──


def select_by_id(
    actions: list[tuple[str, str | None]], *object_ids: str
) -> list[tuple[str, str | None]]:
    """Prepend select-by-id for each object id (F7: selection-tabanlı)."""
    result: list[tuple[str, str | None]] = []
    for oid in object_ids:
        result.append(("select-by-id", oid))
    result.extend(actions)
    return result


# ── Common action chains ──


def chain_query_all() -> list[str]:
    """CLI args for --query-all."""
    return ["--query-all"]


def chain_query_geometry(object_ids: list[str]) -> list[tuple[str, str | None]]:
    """Build action chain to query geometry of specific objects."""
    actions: list[tuple[str, str | None]] = []
    # Select each ID, then query-all
    actions.append(("select-clear", None))
    for oid in object_ids:
        actions.append(("select-by-id", oid))
    actions.append(("query-all", None))
    return actions


def chain_export_png(
    output_path: Path,
    dpi: int | None = None,
    width: int | None = None,
    height: int | None = None,
    background: str | None = None,
    background_opacity: float | None = None,
) -> list[tuple[str, str | None]]:
    """Build export action chain for PNG output."""
    actions: list[tuple[str, str | None]] = [
        ("export-filename", str(output_path)),
        ("export-type", "png"),
    ]
    if dpi is not None:
        actions.append(("export-dpi", str(int(dpi))))
    if width is not None:
        actions.append(("export-width", str(int(width))))
    if height is not None:
        actions.append(("export-height", str(int(height))))
    if background is not None:
        actions.append(("export-background", background))
    if background_opacity is not None:
        actions.append(("export-background-opacity", str(background_opacity)))
    actions.append(("export-do", None))
    return actions


def chain_export_svg(
    output_path: Path,
    plain: bool = False,
    text_to_path: bool = False,
) -> list[tuple[str, str | None]]:
    """Build export action chain for SVG output."""
    actions: list[tuple[str, str | None]] = [
        ("export-filename", str(output_path)),
        ("export-type", "svg"),
    ]
    if plain:
        actions.append(("export-plain-svg", None))
    if text_to_path:
        actions.append(("export-text-to-path", None))
    actions.append(("export-do", None))
    return actions


def chain_path_union(*object_ids: str) -> list[tuple[str, str | None]]:
    """Build action chain for path-union.

    Requires object-to-path first (rect/circle → path), then path-union.
    Returns chain suitable for --actions mode.
    """
    actions: list[tuple[str, str | None]] = []
    # Select each operand, convert to path
    for oid in object_ids:
        actions.append(("select-clear", None))
        actions.append(("select-by-id", oid))
        actions.append(("object-to-path", None))
    # Now select all converted paths and union
    actions.append(("select-clear", None))
    for oid in object_ids:
        actions.append(("select-by-id", oid))
    actions.append(("path-union", None))
    return actions


def chain_set_attribute(
    object_id: str, attr_name: str, attr_value: str
) -> list[tuple[str, str | None]]:
    """Build action chain to set an attribute on an object."""
    return [
        ("select-clear", None),
        ("select-by-id", object_id),
        ("object-set-attribute", f"{attr_name},{attr_value}"),
    ]


def chain_transform_translate(
    object_id: str, dx: float, dy: float
) -> list[tuple[str, str | None]]:
    """Build action chain to translate an object."""
    return [
        ("select-clear", None),
        ("select-by-id", object_id),
        ("transform-translate", f"{dx},{dy}"),
    ]


def chain_path_difference(*object_ids: str) -> list[tuple[str, str | None]]:
    """Build action chain for path-difference (per-operand desen, like chain_path_union)."""
    actions: list[tuple[str, str | None]] = []
    for oid in object_ids:
        actions.append(("select-clear", None))
        actions.append(("select-by-id", oid))
        actions.append(("object-to-path", None))
    actions.append(("select-clear", None))
    for oid in object_ids:
        actions.append(("select-by-id", oid))
    actions.append(("path-difference", None))
    return actions


def chain_path_intersection(*object_ids: str) -> list[tuple[str, str | None]]:
    """Build action chain for path-intersection (per-operand desen)."""
    actions: list[tuple[str, str | None]] = []
    for oid in object_ids:
        actions.append(("select-clear", None))
        actions.append(("select-by-id", oid))
        actions.append(("object-to-path", None))
    actions.append(("select-clear", None))
    for oid in object_ids:
        actions.append(("select-by-id", oid))
    actions.append(("path-intersection", None))
    return actions


def chain_path_exclusion(*object_ids: str) -> list[tuple[str, str | None]]:
    """Build action chain for path-exclusion (per-operand desen)."""
    actions: list[tuple[str, str | None]] = []
    for oid in object_ids:
        actions.append(("select-clear", None))
        actions.append(("select-by-id", oid))
        actions.append(("object-to-path", None))
    actions.append(("select-clear", None))
    for oid in object_ids:
        actions.append(("select-by-id", oid))
    actions.append(("path-exclusion", None))
    return actions


# ── Action validation for run_actions ──


def validate_run_actions(
    actions: list[dict[str, Any]], config: SecurityConfig
) -> list[tuple[str, str | None]]:
    """Validate user-supplied actions for the run_actions escape hatch.

    Each action dict must have: {"name": str, "arg": str | None}
    Returns validated (name, arg) tuples.
    Rejects GUI actions, unknown actions, and invalid args.
    """
    result: list[tuple[str, str | None]] = []
    for entry in actions:
        name = entry.get("name", "")
        arg = entry.get("arg")

        if not _ACTION_NAME_RE.match(name):
            raise InkscapeSecurityError(f"Invalid action name: '{name}'")
        if is_gui_action(name):
            raise InkscapeSecurityError(
                f"Action '{name}' requires GUI — rejected in headless mode"
            )
        if not is_headless_safe(name):
            raise InkscapeSecurityError(
                f"Action '{name}' is not in the headless-safe allowlist"
            )
        if arg is not None:
            if not _ACTION_ARG_RE.match(str(arg)):
                raise InkscapeSecurityError(
                    f"Invalid argument for {name}: '{arg}'"
                )

        result.append((name, arg))
    return result
