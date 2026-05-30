"""
Capabilities introspection: load action-list, build capabilities.json.

Uses the single-source allowlist from security.py (Madde 8: allowlist tek kaynak).
"""
from __future__ import annotations

from pathlib import Path

from .security import _CORE_ALLOWLIST, _GUI_ACTIONS

# Re-export the single source of truth (no duplication)
_HEADLESS_SAFE = _CORE_ALLOWLIST


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


def load_capabilities(project_root: Path) -> dict:
    """Load capabilities from reference file shipped with the server."""
    ref = project_root / "reference" / "action-list-full.txt"
    if ref.exists():
        return build_capabilities(ref)
    return {"error": "action-list-full.txt not found", "total_actions": 0}
