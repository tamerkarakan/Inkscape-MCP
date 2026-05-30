"""
TypedDict return types for FastMCP tool outputSchema generation.

FastMCP auto-generates outputSchema from the tool's return-type annotation.
Each TypedDict matches what the tool ACTUALLY returns (content + structuredContent).

Madde 9: structuredContent dönen her tool artık TypedDict return tipine sahip.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

# ── Content blocks ──


class TextContent(TypedDict):
    """A text content block (used in both success and error responses)."""

    type: str
    text: str


# ── document_create ──


class DocumentCreateStructured(TypedDict):
    """Structured output for document_create."""

    document_path: str
    file_name: str
    revision: int
    width: float
    height: float
    viewBox: str


class DocumentCreateResult(TypedDict):
    """Return type for document_create tool."""

    content: list[TextContent]
    structuredContent: DocumentCreateStructured
    isError: NotRequired[bool]


# ── element_create ──


class ElementCreateStructured(TypedDict):
    """Structured output for element_create."""

    element_id: str
    element_type: str
    revision: int
    px_coords: NotRequired[dict[str, float]]


class ElementCreateResult(TypedDict):
    """Return type for element_create tool."""

    content: list[TextContent]
    structuredContent: ElementCreateStructured
    isError: NotRequired[bool]


# ── element_update ──


class ElementUpdateStructured(TypedDict):
    """Structured output for element_update."""

    object_id: str
    revision: int
    updated_properties: list[str]


class ElementUpdateResult(TypedDict):
    """Return type for element_update tool."""

    content: list[TextContent]
    structuredContent: ElementUpdateStructured
    isError: NotRequired[bool]


# ── query_geometry ──


class GeometryObject(TypedDict):
    """Per-object geometry (user-unit coordinates)."""

    x: float
    y: float
    width: float
    height: float


class DocumentInfo(TypedDict):
    """Document-level info block."""

    width_px: float
    height_px: float
    viewBox: dict[str, float]
    px_to_user_unit: float
    user_unit_to_px: float
    revision: int


class QueryGeometryStructured(TypedDict):
    """Structured output for query_geometry."""

    revision: int
    objects: dict[str, GeometryObject]
    document: DocumentInfo


class QueryGeometryResult(TypedDict):
    """Return type for query_geometry tool."""

    content: list[TextContent]
    structuredContent: QueryGeometryStructured
    isError: NotRequired[bool]


# ── export_document ──


class ExportDocumentStructured(TypedDict):
    """Structured output for export_document."""

    output_path: str
    format: str
    file_size: NotRequired[int]


class ExportDocumentResult(TypedDict):
    """Return type for export_document tool."""

    content: list[TextContent]
    structuredContent: ExportDocumentStructured
    isError: NotRequired[bool]


# ── render_preview ──


class RenderPreviewStructured(TypedDict):
    """Structured output for render_preview."""

    preview_available: bool
    preview_size: NotRequired[int]
    revision: NotRequired[int]
    preview_resource: NotRequired[str]


class RenderPreviewResult(TypedDict):
    """Return type for render_preview tool.

    Note: content may contain TextContent OR ImageContent blocks.
    """

    content: list[dict[str, str]]
    structuredContent: RenderPreviewStructured
    isError: NotRequired[bool]


# ── run_actions ──


class IdMap(TypedDict):
    """id_map block: survived, destroyed, created."""

    survived: dict[str, str]
    destroyed: list[str]
    created: list[str]


class RunActionsStructured(TypedDict):
    """Structured output for run_actions."""

    operation: str
    revision: int
    id_preservation: str
    id_map: IdMap


class RunActionsResult(TypedDict):
    """Return type for run_actions tool."""

    content: list[TextContent]
    structuredContent: RunActionsStructured
    isError: NotRequired[bool]


# ── gui_open ──


class GuiOpenStructured(TypedDict):
    """Structured output for gui_open (live Inkscape GUI session)."""

    app_id: str
    document_path: str
    status: str


# ── gui_apply ──


class GuiApplyStructured(TypedDict):
    """Structured output for gui_apply (action sent to live GUI window)."""

    app_id: str
    operation: str
    status: str


# ── gui_export ──


class GuiExportStructured(TypedDict):
    """Structured output for gui_export (export current live window state)."""

    output_path: str
    format: str
    file_size: NotRequired[int]


# ── gui_close ──


class GuiCloseStructured(TypedDict):
    """Structured output for gui_close (terminate live GUI session)."""

    app_id: str
    status: str


# ── import_image ──


class ImportImageStructured(TypedDict):
    """Structured result for import_image tool."""

    element_id: str
    element_type: str
    revision: int
    width: float
    height: float


# ── trace_bitmap ──


class TraceBitmapStructured(TypedDict):
    """Result from tracing an embedded <image> into <path> geometry."""

    operation: str
    revision: int
    image_id: str
    id_preservation: str
    id_map: IdMap


# ── ask_user ──


class AskUserStructured(TypedDict):
    """Structured result for ask_user (human elicitation)."""

    answered: bool
    action: str
    response: str


# ── workspace_info ──


class WorkspaceInfoStructured(TypedDict):
    """Structured result for workspace_info."""

    workspace_path: str
    files: list[str]
    note: str


# ── write_svg ──


class WriteSvgStructured(TypedDict):
    """Structured result for write_svg."""

    document_path: str
    file_name: str
    revision: int


# ── transform_element ──


class TransformElementStructured(TypedDict):
    """Structured result for transform_element."""

    object_id: str
    revision: int
    transform: str


# ── reorder_element ──


class ReorderElementStructured(TypedDict):
    """Structured result for reorder_element."""

    object_id: str
    revision: int
    position: str
