"""
Inkscape MCP Server — FastMCP-based entry point.

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
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .exceptions import InkscapeError
from .security import SecurityConfig
from .session import SessionManager
from .tools import (
    tool_document_create,
    tool_element_create,
    tool_element_update,
    tool_export,
    tool_query,
    tool_render_preview,
    tool_run_actions,
)
from .resources import (
    resource_capabilities,
    resource_current_svg,
    resource_document_info,
)
from .capabilities import load_capabilities as _load_caps
from .schemas import (
    DocumentCreateResult,
    ElementCreateResult,
    ElementUpdateResult,
    QueryGeometryResult,
    ExportDocumentResult,
    RenderPreviewResult,
    RunActionsResult,
)


def _get_project_root() -> Path:
    """Get project root (parent of src/)."""
    return Path(__file__).resolve().parent.parent.parent


def create_server() -> FastMCP:
    """Build and configure the MCP server."""
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
    project_root = _get_project_root()

    mcp = FastMCP("inkscape-mcp")

    def _to_error(err: InkscapeError) -> dict:
        return {
            "content": [{"type": "text", "text": err.detail}],
            "isError": True,
            "structuredContent": err.to_dict(),
        }

    # ═══════════════════════════════════════════
    #  Tools
    # ═══════════════════════════════════════════

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def document_create(
        width: float = 200.0,
        height: float = 200.0,
        view_box: str | None = None,
        doc_name: str = "document",
    ) -> DocumentCreateResult:
        """Create a new empty SVG document via DOM (no Inkscape CLI)."""
        try:
            return await tool_document_create(
                session_mgr, config,
                width=width, height=height,
                view_box=view_box, doc_name=doc_name,
            )
        except InkscapeError as e:
            return _to_error(e)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def element_create(
        document_path: str,
        element_type: str,
        properties: dict[str, Any],
        expected_revision: int | None = None,
    ) -> ElementCreateResult:
        """Create a new SVG element (rect, circle, path, text) via DOM."""
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def element_update(
        document_path: str,
        object_id: str,
        properties: dict[str, Any],
        expected_revision: int | None = None,
    ) -> ElementUpdateResult:
        """Update properties of existing SVG element via DOM (Madde 12)."""
        try:
            return await tool_element_update(
                session_mgr, config,
                document_path=document_path,
                object_id=object_id,
                properties=properties,
                expected_revision=expected_revision,
            )
        except InkscapeError as e:
            return _to_error(e)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def query_geometry(
        document_path: str,
        object_ids: list[str] | None = None,
    ) -> QueryGeometryResult:
        """Query object bounding boxes (user-unit coordinates)."""
        try:
            return await tool_query(
                session_mgr, config,
                document_path=document_path,
                object_ids=object_ids,
            )
        except InkscapeError as e:
            return _to_error(e)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
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
    ) -> ExportDocumentResult:
        """Export SVG to PNG/SVG/PDF via Inkscape CLI."""
        try:
            return await tool_export(
                session_mgr, config,
                document_path=document_path,
                output_name=output_name,
                export_format=export_format,
                dpi=dpi, width=width, height=height,
                plain_svg=plain_svg, background=background,
                object_ids=object_ids,
                expected_revision=expected_revision,
            )
        except InkscapeError as e:
            return _to_error(e)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def render_preview(
        document_path: str,
        width: int = 400,
        height: int | None = None,
    ) -> RenderPreviewResult:
        """Render a PNG preview of the current SVG."""
        try:
            return await tool_render_preview(
                session_mgr, config,
                document_path=document_path,
                width=width, height=height,
            )
        except InkscapeError as e:
            return _to_error(e)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def run_actions(
        document_path: str,
        operation: str,
        object_ids: list[str],
        action_params: dict[str, Any] | None = None,
        expected_revision: int | None = None,
    ) -> RunActionsResult:
        """Run a headless-safe Inkscape action (path ops, set_attribute, transform).

        id-changing operations return an id_map {survived, destroyed, created}.
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

    @mcp.resource("inkscape://session/capabilities")
    def get_capabilities() -> dict:
        """Inkscape capabilities: action list, headless-safe subset."""
        ref = project_root / "reference" / "action-list-full.txt"
        if ref.exists():
            return _load_caps(project_root)
        return {"error": "action-list-full.txt not found", "total_actions": 0}

    @mcp.resource("inkscape://session/document-info/{document_path}")
    async def get_document_info(document_path: str) -> dict | str:
        """Document info: viewBox, dimensions, conversion factor, revision."""
        try:
            return await resource_document_info(session_mgr, config, document_path)
        except InkscapeError as e:
            return e.to_dict()

    @mcp.resource("inkscape://session/svg/{document_path}")
    async def get_current_svg(document_path: str) -> str:
        """Current SVG content (raw XML) for the given document."""
        try:
            data = await resource_current_svg(session_mgr, config, document_path)
            return data.decode("utf-8", errors="replace")
        except InkscapeError as e:
            return str(e)

    @mcp.resource("inkscape://session/preview/{document_path}")
    async def get_preview(document_path: str) -> str:
        """PNG preview resource (base64) for the current SVG document."""
        try:
            result = await tool_render_preview(
                session_mgr, config,
                document_path=document_path,
            )
            if result.get("isError"):
                return str(result.get("content", [{}])[0].get("text", "Preview error"))
            for item in result.get("content", []):
                if item.get("type") == "image":
                    return item.get("data", "")
            sc = result.get("structuredContent", {})
            preview_path = sc.get("preview_resource", "")
            return str(preview_path) if preview_path else "Preview unavailable"
        except InkscapeError as e:
            return str(e)

    @mcp.resource("inkscape://session/list")
    def list_sessions() -> dict:
        """List all open document sessions."""
        return {
            "sessions": {
                key: {
                    "revision": state.revision,
                    "last_access": state.last_access,
                }
                for key, state in session_mgr._documents.items()
            }
        }

    # ── Cold-start warm-up (background; non-blocking) ──
    async def _warmup_inkscape() -> None:
        """Pre-warm Inkscape binary to avoid >30s cold-start timeout."""
        import tempfile
        warmup_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"
     viewBox="0 0 10 10">
  <rect id="w" x="1" y="1" width="8" height="8"/>
</svg>"""
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".svg", delete=False, mode="w", encoding="utf-8"
            ) as f:
                f.write(warmup_svg)
                tmp_path = f.name
            try:
                binary = os.environ.get(
                    "INKSCAPE_BIN",
                    "inkscape.com" if os.name == "nt" else "inkscape",
                )
                proc = await asyncio.create_subprocess_exec(
                    binary, "--query-all", tmp_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.communicate(), timeout=60)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        except Exception:
            pass  # Warm-up failure is non-fatal

    # Store warm-up coroutine for run() to schedule
    mcp._warmup = _warmup_inkscape

    return mcp


async def run() -> None:
    """Run the MCP server over stdio transport."""
    server = create_server()
    # Schedule cold-start warm-up in background
    warmup = getattr(server, "_warmup", None)
    if warmup:
        asyncio.create_task(warmup())
    await server.run_stdio_async()


def main() -> None:
    """Entry point."""
    import asyncio
    asyncio.run(run())


if __name__ == "__main__":
    main()
