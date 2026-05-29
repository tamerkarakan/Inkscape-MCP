"""
MCP Resource definitions: exposes session state as read-only resources.
"""
from __future__ import annotations

from .capabilities import load_capabilities
from .security import SecurityConfig
from .session import SessionManager


async def resource_current_svg(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
) -> bytes:
    """Return the current SVG content (raw XML)."""
    from pathlib import Path
    from .security import validate_path
    svg_path = validate_path(Path(document_path), config)
    await session_mgr.get_or_open(svg_path)
    return svg_path.read_bytes()


async def resource_document_info(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
) -> dict:
    """Return document info: viewBox, dimensions, conversion factor, revision."""
    from pathlib import Path
    from .security import validate_path
    from .normalize import normalize_document_info

    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)

    return normalize_document_info(
        state.width_px,
        state.height_px,
        state.view_box,
        state.px_to_user_unit,
        state.revision,
    )


def resource_capabilities(config: SecurityConfig) -> dict:
    """Return capabilities document (action list, headless-safe subset)."""
    return load_capabilities(config.workspace_root)
