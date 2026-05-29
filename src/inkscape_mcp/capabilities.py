"""
Capabilities introspection: load action-list, build capabilities.json.
"""
from __future__ import annotations

from pathlib import Path

# Known headless-safe actions (subset of core-actions.txt confirmed working)
_HEADLESS_SAFE = {
    # Selection
    "select-by-id", "select-all", "select-clear", "select-invert",
    "select-list", "unselect-by-id",
    # Query
    "query-all", "query-x", "query-y", "query-width", "query-height",
    # Mutation
    "object-set-attribute", "object-set-property",
    # Path ops
    "object-to-path", "object-stroke-to-path",
    "path-union", "path-difference", "path-intersection", "path-exclusion",
    "path-division", "path-combine", "path-break-apart",
    "path-simplify", "path-flatten", "path-fracture", "path-split",
    # Transform
    "transform-translate", "transform-scale",
    "transform-rotate", "object-flip-horizontal", "object-flip-vertical",
    "object-rotate-90-cw", "object-rotate-90-ccw",
    # Delete / duplicate
    "delete", "delete-selection", "duplicate",
    # Stack order
    "selection-top", "selection-bottom",
    "selection-raise", "selection-lower",
    # Group
    "selection-group", "selection-ungroup",
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
    "swap-fill-and-stroke", "edit-remove-filter",
}

# GUI-only — always rejected
_GUI_ACTIONS = {
    "window-open", "window-close", "window-crash",
    "window-query-geometry", "window-set-geometry",
    "active-window-start", "active-window-end",
    "file-open-window",
}


def load_action_list_from_file(path: Path) -> dict[str, str]:
    """Parse action-list dump into {name: description} dict."""
    actions: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            name, _, desc = line.partition(":")
            name = name.strip()
            desc = desc.strip()
            if name:
                actions[name] = desc
    return actions


def build_capabilities(action_list_path: Path) -> dict:
    """Build capabilities document from action-list snapshot.

    Pinned to the binary version the snapshot was produced from.
    """
    all_actions = load_action_list_from_file(action_list_path)

    headless = {}
    gui_only = {}
    unknown = {}

    for name, desc in all_actions.items():
        if name in _GUI_ACTIONS:
            gui_only[name] = desc
        elif name in _HEADLESS_SAFE:
            headless[name] = desc
        else:
            unknown[name] = desc

    return {
        "inkscape_version": "1.4.2",
        "inkscape_revision": "f4327f4",
        "total_actions": len(all_actions),
        "headless_safe_count": len(headless),
        "gui_only_count": len(gui_only),
        "unverified_count": len(unknown),
        "headless_safe": headless,
        "gui_only": gui_only,
        "export_formats": ["svg", "png", "pdf", "ps", "eps", "emf", "wmf", "xaml"],
    }


def load_capabilities(workspace_root: Path) -> dict:
    """Load capabilities from reference file shipped with the server."""
    ref = workspace_root / "reference" / "action-list-full.txt"
    if ref.exists():
        return build_capabilities(ref)
    return {"error": "action-list-full.txt not found", "total_actions": 0}
