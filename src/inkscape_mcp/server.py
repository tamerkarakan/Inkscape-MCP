"""
Inkscape MCP Server — stdio transport entry point.

Usage:
    python -m inkscape_mcp.server

Environment variables:
    INKSCAPE_BIN          Path to inkscape.com (required)
    INKSCAPE_WORKSPACE    Workspace root directory (default: ./workspace)
    INKSCAPE_TIMEOUT      Default command timeout seconds (default: 30)
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server

from .exceptions import (
    InkscapeError,
)
from .security import SecurityConfig
from .session import SessionManager
from .tools import (
    tool_document_create,
    tool_element_create,
    tool_export,
    tool_query,
    tool_render_preview,
    tool_run_actions,
)
from .resources import resource_capabilities, resource_document_info


def create_server() -> Server:
    """Build and configure the MCP server instance."""
    # ── Configuration ──
    workspace = Path(
        os.environ.get("INKSCAPE_WORKSPACE",
                       str(Path.cwd() / "workspace"))
    )
    workspace.mkdir(parents=True, exist_ok=True)

    config = SecurityConfig(
        workspace_root=workspace,
        default_timeout=int(os.environ.get("INKSCAPE_TIMEOUT", "30")),
    )

    session_mgr = SessionManager(config)

    app = Server("inkscape-mcp")

    # ═══════════════════════════════════════════
    #  Tools
    # ═══════════════════════════════════════════

    @app.tool()
    async def document_create(
        width: float = 200.0,
        height: float = 200.0,
        view_box: str | None = None,
        doc_name: str = "document",
    ) -> dict:
        """Create a new empty SVG document.

        The document is created via DOM (lxml) — never through Inkscape CLI.
        Returns the document path, name, and initial revision.
        """
        try:
            return await tool_document_create(
                session_mgr, config,
                width=width, height=height,
                view_box=view_box, doc_name=doc_name,
            )
        except InkscapeError as e:
            return _to_error(e)

    @app.tool()
    async def element_create(
        document_path: str,
        element_type: str,
        properties: dict,
        expected_revision: int | None = None,
    ) -> dict:
        """Create a new SVG element (rect, circle, path, text) via DOM.

        Args:
            document_path: Path to the SVG document (within workspace).
            element_type: One of 'rect', 'circle', 'path', 'text'.
            properties: Element properties (x, y, width, height, fill, stroke, etc.).
            expected_revision: Optional expected revision for optimistic locking.

        Returns the new element's ID and updated revision.
        id_preservation: preserving (no existing IDs destroyed).
        """
        try:
            return await tool_element_create(
                session_mgr, config,
                document_path=document_path,
                element_type=element_type,
                properties=properties,
                expected_revision=expected_revision,
            )
        except InkscapeError as e:
            return _to_error(e)

    @app.tool()
    async def query_geometry(
        document_path: str,
        object_ids: list[str] | None = None,
    ) -> dict:
        """Query object bounding boxes via Inkscape CLI.

        Returns user-unit coordinates (px→user-unit conversion applied internally).
        All I/O in user-unit space (viewBox coordinates).
        """
        try:
            return await tool_query(
                session_mgr, config,
                document_path=document_path,
                object_ids=object_ids,
            )
        except InkscapeError as e:
            return _to_error(e)

    @app.tool()
    async def export_document(
        document_path: str,
        output_name: str,
        export_format: str = "png",
        dpi: int | None = None,
        width: int | None = None,
        height: int | None = None,
        plain_svg: bool = False,
        background: str | None = None,
        object_ids: list[str] | None = None,
        expected_revision: int | None = None,
    ) -> dict:
        """Export SVG to PNG, SVG, PDF, or other formats via Inkscape CLI.

        Output is written inside the workspace directory.
        """
        try:
            return await tool_export(
                session_mgr, config,
                document_path=document_path,
                output_name=output_name,
                export_format=export_format,
                dpi=dpi, width=width, height=height,
                plain_svg=plain_svg,
                background=background,
                object_ids=object_ids,
                expected_revision=expected_revision,
            )
        except InkscapeError as e:
            return _to_error(e)

    @app.tool()
    async def render_preview(
        document_path: str,
        width: int = 400,
        height: int | None = None,
    ) -> dict:
        """Render a PNG preview of the current SVG for visual feedback.

        Returns inline base64-encoded PNG (if under preview size limit)
        or a resource_link for large previews.
        preview_available is always returned for mutation tool annotations.
        """
        try:
            return await tool_render_preview(
                session_mgr, config,
                document_path=document_path,
                width=width, height=height,
            )
        except InkscapeError as e:
            return _to_error(e)

    @app.tool()
    async def run_actions(
        document_path: str,
        operation: str,
        object_ids: list[str],
        action_params: dict | None = None,
        expected_revision: int | None = None,
    ) -> dict:
        """Run a headless-safe Inkscape action (escape hatch).

        Supported operations: path_union, path_difference, path_intersection,
        path_exclusion, set_attribute, transform_translate.

        id-changing operations (path_union etc.) return an id_map:
        {survived: {old→new}, destroyed: [...], created: [...]}
        (Madde 14/F8).

        All action names are validated against the headless-safe allowlist.
        GUI actions and unknown actions are rejected.
        """
        try:
            return await tool_run_actions(
                session_mgr, config,
                document_path=document_path,
                operation=operation,
                object_ids=object_ids,
                action_params=action_params,
                expected_revision=expected_revision,
            )
        except InkscapeError as e:
            return _to_error(e)

    # ═══════════════════════════════════════════
    #  Resources
    # ═══════════════════════════════════════════

    @app.resource("inkscape://session/capabilities")
    def get_capabilities() -> dict:
        """Inkscape capabilities: action list, headless-safe subset."""
        return resource_capabilities(config)

    @app.resource("inkscape://session/document-info")
    async def get_document_info(document_path: str) -> dict:
        """Document info: viewBox, dimensions, conversion factor, revision."""
        try:
            return await resource_document_info(session_mgr, config, document_path)
        except InkscapeError as e:
            return _to_error(e)

    return app


def _to_error(err: InkscapeError) -> dict:
    """Convert an InkscapeError to MCP isError result."""
    return {
        "content": [{"type": "text", "text": err.detail}],
        "isError": True,
        "structuredContent": err.to_dict(),
    }


async def run() -> None:
    """Run the MCP server over stdio transport."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """Entry point for python -m inkscape_mcp.server"""
    import asyncio
    asyncio.run(run())


if __name__ == "__main__":
    main()
