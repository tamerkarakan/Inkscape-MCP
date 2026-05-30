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

import asyncio
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP, Image
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
    _render_preview_png,
    tool_run_actions,
    tool_gui_open,
    tool_gui_apply,
    tool_gui_export,
    tool_gui_close,
    tool_import_image,
    tool_trace_bitmap,
    tool_ask_user,
    tool_workspace_info,
    tool_write_svg,
    tool_transform_element,
    tool_reorder_element,
    tool_create_gradient,
    tool_create_pattern,
)
from .gui_session import GuiSessionManager
from .resources import (
    resource_capabilities,
    resource_current_svg,
    resource_document_info,
)
from .capabilities import load_capabilities as _load_caps
from .schemas import (
    DocumentCreateStructured as DocumentCreateResult,
    ElementCreateStructured as ElementCreateResult,
    ElementUpdateStructured as ElementUpdateResult,
    QueryGeometryStructured as QueryGeometryResult,
    ExportDocumentStructured as ExportDocumentResult,
    RenderPreviewStructured as RenderPreviewResult,
    RunActionsStructured as RunActionsResult,
    GuiOpenStructured as GuiOpenResult,
    GuiApplyStructured as GuiApplyResult,
    GuiExportStructured as GuiExportResult,
    GuiCloseStructured as GuiCloseResult,
    ImportImageStructured as ImportImageResult,
    TraceBitmapStructured as TraceBitmapResult,
    AskUserStructured as AskUserResult,
    WorkspaceInfoStructured as WorkspaceInfoResult,
    WriteSvgStructured as WriteSvgResult,
    TransformElementStructured as TransformElementResult,
    ReorderElementStructured as ReorderElementResult,
    CreateGradientStructured as CreateGradientResult,
    CreatePatternStructured as CreatePatternResult,
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
    gui_mgr = GuiSessionManager(config)
    project_root = _get_project_root()

    mcp = FastMCP(
        "inkscape-mcp",
        instructions=(
            "Inkscape SVG editor. AFTER ANY tool that modifies a document "
            "(write_svg, element_create/update, transform_element, "
            "reorder_element, create_gradient/pattern, import_image, "
            "trace_bitmap, run_actions), call render_preview as the LAST step so "
            "the user SEES the result — do not wait to be asked. "
            "Authoring: capable clients may emit the whole SVG in one write_svg "
            "call; otherwise build incrementally with element_create (which the "
            "MCP turns into valid SVG). Files: call workspace_info to learn where "
            "to put input images and find outputs; keep everything under that "
            "directory."
        ),
    )

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
        """Create a new empty SVG document and return its {document_path}.

        width/height are the canvas size in user units. view_box defaults to
        "0 0 width height"; pass it explicitly to decouple the coordinate system
        from the pixel size. Use the returned document_path in every later call
        (element_create, render_preview, export_document, ...). Files land in the
        workspace (see workspace_info).
        """
        try:
            return await tool_document_create(
                session_mgr, config,
                width=width, height=height,
                view_box=view_box, doc_name=doc_name,
            )
        except InkscapeError:
            raise

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
        before_id: str | None = None,
    ) -> ElementCreateResult:
        """Create one SVG element via DOM and return its generated id.

        element_type + the keys to put in `properties` (units = user units):
          - "rect":    x, y, width, height; optional rx, ry (corner radius)
          - "circle":  cx, cy, r
          - "ellipse": cx, cy, rx, ry  (use this for ovals — no arc-path needed)
          - "path":    d  (an SVG path data string, e.g. "M10 10 L90 90 Z")
          - "text":    x, y, text; optional font_family, font_size

        Paint/style keys work on any type: fill, stroke, stroke_width, opacity,
        fill_opacity, stroke_opacity, stroke_dasharray, stroke_linecap,
        stroke_linejoin, transform, ... Both snake_case (stroke_width) and the
        raw SVG hyphen name (stroke-width) are accepted; any key not consumed by
        the type above passes straight through to the SVG attribute, so nothing
        is silently dropped. fill/stroke take a CSS color ("#ff0000", "red") or
        "url(#id)" from create_gradient/create_pattern, or "none".

        Example: element_create(document_path=..., element_type="rect",
          properties={"x":10,"y":10,"width":80,"height":40,"rx":6,
                      "fill":"#3366cc","stroke":"black","stroke_width":2})

        Appends on top (end of document = highest z-order) by default. Pass
        before_id to insert this element directly BENEATH an existing one
        (e.g. a shadow under a shape); see reorder_element to restack later.
        """
        try:
            return await tool_element_create(
                session_mgr, config,
                document_path=document_path,
                element_type=element_type,
                properties=properties,
                expected_revision=expected_revision,
                before_id=before_id,
            )
        except InkscapeError:
            raise

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
        """Change attributes of an existing element (found by object_id) via DOM.

        `properties` uses the SAME keys as element_create: geometry (x, y, width,
        height, cx, cy, r, rx, ry, d, text, ...) and paint/style (fill, stroke,
        stroke_width, opacity, transform, "url(#id)" fills, ...). Only the keys
        you pass are changed; others are left as-is. snake_case and hyphenated
        SVG names both work; unknown keys pass through to the attribute.
        """
        try:
            return await tool_element_update(
                session_mgr, config,
                document_path=document_path,
                object_id=object_id,
                properties=properties,
                expected_revision=expected_revision,
            )
        except InkscapeError:
            raise

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
        except InkscapeError:
            raise

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
        except InkscapeError:
            raise

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
    ) -> Image:
        """Render a PNG preview of the current SVG (returned as an inline image)."""
        try:
            return await tool_render_preview(
                session_mgr, config,
                document_path=document_path,
                width=width, height=height,
            )
        except InkscapeError:
            raise

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
        ctx: Context = None,
    ) -> RunActionsResult:
        """Run a headless-safe Inkscape action on existing elements.

        operation + how object_ids / action_params are used:
          - "path_union" / "path_difference" / "path_intersection" /
            "path_exclusion": boolean-combine 2+ paths in object_ids into one
            new path (order matters for difference). DESTRUCTIVE — the inputs
            are consumed; may prompt the user to confirm.
          - "set_attribute": set one attribute on object_ids[0];
            action_params={"attribute": <name>, "value": <value>}
          - "transform_translate": shift object_ids[0] by
            action_params={"dx": <n>, "dy": <n>} (baked into x/y, not a transform).
            For scale/rotate/skew use transform_element instead.

        Because path ops change ids, the result includes an id_map
        {survived, destroyed, created} — read `created` for the new path id.
        Values may not contain ';' or ':' (action-injection guard).
        """
        try:
            return await tool_run_actions(
                session_mgr, config,
                document_path=document_path,
                operation=operation,
                object_ids=object_ids,
                action_params=action_params,
                expected_revision=expected_revision,
                ctx=ctx,
            )
        except InkscapeError:
            raise

    # ═══════════════════════════════════════════
    #  GUI tools (live --active-window driver)
    # ═══════════════════════════════════════════

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def gui_open(document_path: str) -> GuiOpenResult:
        """Open (or reuse) a VISIBLE Inkscape GUI window for the document."""
        try:
            return await tool_gui_open(gui_mgr, config, document_path=document_path)
        except InkscapeError:
            raise

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def gui_apply(
        document_path: str,
        operation: str,
        object_ids: list[str],
        action_params: dict[str, Any] | None = None,
    ) -> GuiApplyResult:
        """Apply a headless-safe action to the live GUI window (in-memory edit)."""
        try:
            return await tool_gui_apply(
                gui_mgr, config,
                document_path=document_path,
                operation=operation,
                object_ids=object_ids,
                action_params=action_params,
            )
        except InkscapeError:
            raise

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def gui_export(
        document_path: str,
        output_name: str,
        export_format: str = "svg",
    ) -> GuiExportResult:
        """Export the CURRENT live-window state to a file."""
        try:
            return await tool_gui_export(
                gui_mgr, config,
                document_path=document_path,
                output_name=output_name,
                export_format=export_format,
            )
        except InkscapeError:
            raise

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def gui_close(document_path: str) -> GuiCloseResult:
        """Close the live GUI window for the document (terminate the session)."""
        try:
            return await tool_gui_close(gui_mgr, config, document_path=document_path)
        except InkscapeError:
            raise

    # ═══════════════════════════════════════════
    #  Image tools (raster import + trace-bitmap)
    # ═══════════════════════════════════════════

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def import_image(
        document_path: str,
        image_path: str | None = None,
        x: float = 0.0,
        y: float = 0.0,
        width: float | None = None,
        height: float | None = None,
        expected_revision: int | None = None,
        image_data: str | None = None,
        image_format: str = "png",
    ) -> ImportImageResult:
        """Embed a raster into the SVG via DOM.

        Source is either image_path (a file in the workspace) OR image_data
        (base64 bytes + image_format) — the latter lets you embed a chat-pasted
        image that has no file on disk.
        """
        try:
            return await tool_import_image(
                session_mgr, config,
                document_path=document_path, image_path=image_path,
                x=x, y=y, width=width, height=height,
                expected_revision=expected_revision,
                image_data=image_data, image_format=image_format,
            )
        except InkscapeError:
            raise

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def trace_bitmap(
        document_path: str,
        image_id: str,
        scans: int = 2,
        smooth: bool = False,
        stack: bool = True,
        remove_background: bool = False,
        speckles: int = 2,
        smooth_corners: float = 1.0,
        optimize: bool = True,
        remove_source: bool = False,
        expected_revision: int | None = None,
        ctx: Context = None,
    ) -> TraceBitmapResult:
        """Trace an embedded <image> into <path> geometry (Inkscape object-trace)."""
        try:
            return await tool_trace_bitmap(
                session_mgr, config,
                document_path=document_path, image_id=image_id,
                scans=scans, smooth=smooth, stack=stack,
                remove_background=remove_background, speckles=speckles,
                smooth_corners=smooth_corners, optimize=optimize,
                remove_source=remove_source, expected_revision=expected_revision,
                ctx=ctx,
            )
        except InkscapeError:
            raise

    # ═══════════════════════════════════════════
    #  Interaction (MCP elicitation)
    # ═══════════════════════════════════════════

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def ask_user(
        question: str,
        options: list[str] | None = None,
        ctx: Context = None,
    ) -> AskUserResult:
        """Ask the human (behind the client) a structured question via elicitation."""
        return await tool_ask_user(ctx, question, options)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def workspace_info() -> WorkspaceInfoResult:
        """Get the MCP working directory: where to put input files and find outputs."""
        return tool_workspace_info(config)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def write_svg(
        doc_name: str,
        svg_content: str,
    ) -> WriteSvgResult:
        """Author a full SVG document in one call (validated, saved to workspace).

        Fast path for capable clients: emit the whole SVG at once instead of
        many element_create calls. element_create remains for incremental edits
        and weak/low-context clients.
        """
        try:
            return await tool_write_svg(
                session_mgr, config,
                doc_name=doc_name, svg_content=svg_content,
            )
        except InkscapeError:
            raise

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def transform_element(
        document_path: str,
        object_id: str,
        operation: str,
        params: dict[str, Any] | None = None,
        expected_revision: int | None = None,
    ) -> TransformElementResult:
        """Move/scale/rotate/shear an element; composes onto its transform attr.

        operation + the keys to put in `params`:
          - "translate": dx, dy                (shift, in user units)
          - "scale":     sx[, sy]              (sy defaults to sx = uniform;
                                                give sx≠sy to make an oval from a circle)
          - "rotate":    angle[, cx, cy]       (degrees; cx,cy = pivot, else origin)
          - "skew_x":    angle                 (degrees — horizontal shear)
          - "skew_y":    angle                 (degrees — vertical shear)

        Each call APPENDS to any existing transform (does not replace it), so
        repeated calls stack. Example: rotate 30° about (50,50):
          transform_element(..., operation="rotate", params={"angle":30,"cx":50,"cy":50})
        """
        try:
            return await tool_transform_element(
                session_mgr, config,
                document_path=document_path, object_id=object_id,
                operation=operation, params=params,
                expected_revision=expected_revision,
            )
        except InkscapeError:
            raise

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def reorder_element(
        document_path: str,
        object_id: str,
        position: str,
        expected_revision: int | None = None,
    ) -> ReorderElementResult:
        """Restack an element in z-order (paint order = document order).

        position:
          - "top":    move to front (drawn last, above everything)
          - "bottom": move to back  (drawn first, behind everything)
          - "up":     swap forward one step (above the next sibling)
          - "down":   swap backward one step (below the previous sibling)

        "up"/"down" are no-ops at the respective edge. To insert a NEW element
        below an existing one in a single call, use element_create(before_id=...).
        """
        try:
            return await tool_reorder_element(
                session_mgr, config,
                document_path=document_path, object_id=object_id,
                position=position, expected_revision=expected_revision,
            )
        except InkscapeError:
            raise

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def create_gradient(
        document_path: str,
        gradient_type: str,
        stops: list[dict[str, Any]],
        params: dict[str, Any] | None = None,
        expected_revision: int | None = None,
    ) -> CreateGradientResult:
        """Define a linear/radial gradient in <defs>; returns {gradient_id}.

        Apply it by setting an element's fill (or stroke) to "url(#<gradient_id>)".

        gradient_type: "linear" or "radial".
        stops: a list of color stops, each a dict:
          {"offset": 0..1, "color": "#rrggbb"[, "opacity": 0..1]}
          e.g. [{"offset":0,"color":"#ffffff"},{"offset":1,"color":"#0000ff"}]
        params (user-space coords, optional):
          - linear: x1, y1, x2, y2   (gradient axis; default 0,0 → 1,0)
          - radial: cx, cy, r[, fx, fy]   (center+radius; fx,fy = focal point)

        Example: create_gradient(..., gradient_type="linear",
          stops=[{"offset":0,"color":"red"},{"offset":1,"color":"yellow"}],
          params={"x1":0,"y1":0,"x2":200,"y2":0})
        then element_update(..., properties={"fill":"url(#<gradient_id>)"}).
        """
        try:
            return await tool_create_gradient(
                session_mgr, config,
                document_path=document_path, gradient_type=gradient_type,
                stops=stops, params=params, expected_revision=expected_revision,
            )
        except InkscapeError:
            raise

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def create_pattern(
        document_path: str,
        width: float,
        height: float,
        content_svg: str,
        expected_revision: int | None = None,
    ) -> CreatePatternResult:
        """Define a repeating tile <pattern> in <defs>; returns {pattern_id}.

        Apply it by setting an element's fill to "url(#<pattern_id>)".

        width, height: the tile size in user units (the motif repeats every
          width × height).
        content_svg: a raw SVG fragment (one or more elements) drawn inside one
          tile, in tile-local coordinates 0..width / 0..height. No <svg> wrapper.
          e.g. '<circle cx="5" cy="5" r="3" fill="black"/>'

        Example: create_pattern(..., width=10, height=10,
          content_svg='<rect width="5" height="5" fill="#ccc"/>')
        then element_update(..., properties={"fill":"url(#<pattern_id>)"}).
        """
        try:
            return await tool_create_pattern(
                session_mgr, config,
                document_path=document_path, width=width, height=height,
                content_svg=content_svg, expected_revision=expected_revision,
            )
        except InkscapeError:
            raise

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
            png_data, _revision = await _render_preview_png(
                session_mgr, config, document_path=document_path,
            )
            import base64
            return base64.b64encode(png_data).decode()
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

    # ═══════════════════════════════════════════
    #  Prompts (client-AI guidance)
    # ═══════════════════════════════════════════

    @mcp.prompt(
        name="vectorize_image",
        title="Vectorize Image (AI-First)",
        description="Convert an uploaded image to clean, semantic SVG vectors using AI understanding, not trace-bitmap"
    )
    def vectorize_image(document_path: str = "", instructions: str = "") -> str:
        """Guidance for the AI to vectorize an image by understanding its content."""
        base = f"""
You are vectorizing an image the user has already shown you (you can see it in the conversation context).

{("The user gave specific instructions: " + instructions) if instructions else ""}

Follow these steps in order:

1. **ANALYZE the image semantically first.**
   Identify each distinct object, shape, and text element. For each one, determine:
   - What it IS (e.g. a circle, a letter, a logo, a rectangle, an arrow)
   - Its color, fill, and stroke
   - Its position (x,y) and size (width, height, radius)
   - Understanding comes FIRST — do not blindly trace edges.

2. **Set up the SVG document.**
   {"The document_path provided is: " + document_path if document_path else "If document_path is empty, call `document_create()` first. Choose a view_box that preserves the image's aspect ratio (e.g., '0 0 width height')."}
   Use the given `document_path` if non-empty; otherwise use the one you created.

3. **RECONSTRUCT each element with primitive shapes.**
   For each object you identified, call `element_create()` with:
   - `element_type`: one of "rect", "circle", "path", or "text" — choose the CLOSEST semantic primitive.
     * A circle or ellipse → "circle" (use cx, cy, r)
     * A rectangle or rounded rect → "rect" (use x, y, width, height, rx, ry)
     * A letter or word → "text" (use x, y, text, font_family, font_size, fill)
     * Anything complex (logo curves, icons, arrows) → "path" (use d with clean path commands)
   - `properties`: a dict with real coordinates, fills, strokes — match the original image closely.
   - Build clean, intentional vectors, not messy traced points.

4. **SELF-CHECK with `render_preview()` and `query_geometry()`.**
   After creating all elements, generate a `render_preview()` to visually compare against the original image. Use `query_geometry()` to verify bounding boxes and positions. If something is off, call `element_update()` to adjust properties (pass the correct expected_revision). Iterate until the vector version matches the original image closely.

5. **FALLBACK RULE — IMPORTANT:**
   - **Never** use Inkscape's trace-bitmap as your primary vectorization method. It does not understand the image; it only follows color and contour edges.
   - Only use trace-bitmap as a last resort for photographic regions, complex textures, or gradients that genuinely cannot be described as discrete shapes.
   - Everywhere else, use the semantic AI reconstruction method (steps 1-4).

6. **When in doubt, ASK the user.**
   If you cannot determine the intended color, shape meaning, or layout of a part of the image, do not guess — ask the user for clarification before proceeding.
"""
        return base

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
    # Store GUI session manager so run() can close windows on shutdown
    mcp._gui_mgr = gui_mgr

    return mcp


async def run() -> None:
    """Run the MCP server over stdio transport."""
    server = create_server()
    # Schedule cold-start warm-up in background
    warmup = getattr(server, "_warmup", None)
    if warmup:
        asyncio.create_task(warmup())
    try:
        await server.run_stdio_async()
    finally:
        gui_mgr = getattr(server, "_gui_mgr", None)
        if gui_mgr is not None:
            try:
                await gui_mgr.close_all()
            except Exception:
                pass


def main() -> None:
    """Entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
