"""
JSON Schema definitions for FastMCP tool output schemas.

Madde 9: structuredContent dönen her tool'a outputSchema deklare et.
"""

from __future__ import annotations

# ── document_create output ──

DOCUMENT_CREATE_OUTPUT: dict = {
    "type": "object",
    "properties": {
        "content": {
            "type": "array",
            "items": {"type": "object", "properties": {"type": {"type": "string"}, "text": {"type": "string"}}},
        },
        "structuredContent": {
            "type": "object",
            "properties": {
                "document_path": {"type": "string", "description": "Absolute path to the created SVG file"},
                "file_name": {"type": "string", "description": "Filename of the created SVG"},
                "revision": {"type": "integer", "description": "Document revision number (starts at 1)"},
                "width": {"type": "number", "description": "Document width in user units"},
                "height": {"type": "number", "description": "Document height in user units"},
                "viewBox": {"type": "string", "description": "SVG viewBox attribute value"},
            },
            "required": ["document_path", "file_name", "revision", "width", "height", "viewBox"],
        },
    },
}

# ── element_create output ──

ELEMENT_CREATE_OUTPUT: dict = {
    "type": "object",
    "properties": {
        "content": {
            "type": "array",
            "items": {"type": "object", "properties": {"type": {"type": "string"}, "text": {"type": "string"}}},
        },
        "structuredContent": {
            "type": "object",
            "properties": {
                "element_id": {"type": "string", "description": "UUID-based SVG element id (e.g. rect_a1b2c3d4e5f6)"},
                "element_type": {"type": "string", "description": "SVG element type: rect, circle, path, text"},
                "revision": {"type": "integer", "description": "New document revision after creation"},
                "px_coords": {
                    "type": "object",
                    "description": "Pixel-equivalent coordinates (x, y, cx, cy, r, width, height)",
                    "additionalProperties": {"type": "number"},
                },
            },
            "required": ["element_id", "element_type", "revision"],
        },
    },
}

# ── element_update output ──

ELEMENT_UPDATE_OUTPUT: dict = {
    "type": "object",
    "properties": {
        "content": {
            "type": "array",
            "items": {"type": "object", "properties": {"type": {"type": "string"}, "text": {"type": "string"}}},
        },
        "structuredContent": {
            "type": "object",
            "properties": {
                "object_id": {"type": "string", "description": "Updated SVG element id"},
                "revision": {"type": "integer", "description": "New document revision after update"},
                "updated_properties": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of property names that were updated",
                },
            },
            "required": ["object_id", "revision", "updated_properties"],
        },
    },
}

# ── query_geometry output ──

QUERY_GEOMETRY_OUTPUT: dict = {
    "type": "object",
    "properties": {
        "content": {
            "type": "array",
            "items": {"type": "object", "properties": {"type": {"type": "string"}, "text": {"type": "string"}}},
        },
        "structuredContent": {
            "type": "object",
            "properties": {
                "revision": {"type": "integer", "description": "Current document revision"},
                "objects": {
                    "type": "object",
                    "description": "Map of object_id → {x, y, width, height} in user-unit coordinates",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                        },
                    },
                },
                "document": {
                    "type": "object",
                    "description": "Document-level info (viewBox, dimensions, unit conversion, revision)",
                    "properties": {
                        "width_px": {"type": "number"},
                        "height_px": {"type": "number"},
                        "viewBox": {
                            "type": "object",
                            "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "width": {"type": "number"}, "height": {"type": "number"}},
                        },
                        "px_to_user_unit": {"type": "number"},
                        "user_unit_to_px": {"type": "number"},
                        "revision": {"type": "integer"},
                    },
                },
            },
            "required": ["revision", "objects", "document"],
        },
    },
}

# ── export_document output ──

EXPORT_DOCUMENT_OUTPUT: dict = {
    "type": "object",
    "properties": {
        "content": {
            "type": "array",
            "items": {"type": "object", "properties": {"type": {"type": "string"}, "text": {"type": "string"}}},
        },
        "structuredContent": {
            "type": "object",
            "properties": {
                "output_path": {"type": "string", "description": "Absolute path to the exported file"},
                "format": {"type": "string", "description": "Export format (png, svg, pdf, etc.)"},
                "file_size": {"type": "integer", "description": "Size of exported file in bytes"},
            },
            "required": ["output_path", "format"],
        },
    },
}

# ── render_preview output ──

RENDER_PREVIEW_OUTPUT: dict = {
    "type": "object",
    "properties": {
        "content": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "object", "properties": {"type": {"const": "text"}, "text": {"type": "string"}}},
                    {"type": "object", "properties": {"type": {"const": "image"}, "data": {"type": "string"}, "mimeType": {"const": "image/png"}}},
                ],
            },
        },
        "structuredContent": {
            "type": "object",
            "properties": {
                "preview_available": {"type": "boolean", "description": "Whether a preview was rendered"},
                "preview_size": {"type": "integer", "description": "Size of preview PNG in bytes (if inline)"},
                "revision": {"type": "integer", "description": "Document revision at time of preview"},
                "preview_resource": {"type": "string", "description": "Resource URI for large previews that exceed inline limit"},
            },
        },
    },
}

# ── run_actions output ──

RUN_ACTIONS_OUTPUT: dict = {
    "type": "object",
    "properties": {
        "content": {
            "type": "array",
            "items": {"type": "object", "properties": {"type": {"type": "string"}, "text": {"type": "string"}}},
        },
        "structuredContent": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "description": "The operation that was performed"},
                "revision": {"type": "integer", "description": "New document revision after the operation"},
                "id_preservation": {
                    "type": "string",
                    "enum": ["preserving", "changing"],
                    "description": "Whether the operation preserved or changed element IDs",
                },
                "id_map": {
                    "type": "object",
                    "description": "Map of ID changes: {survived: {old→new}, destroyed: [...], created: [...]}",
                    "properties": {
                        "survived": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                            "description": "IDs that survived the operation (old_id → new_id)",
                        },
                        "destroyed": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "IDs that were destroyed by the operation",
                        },
                        "created": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "New IDs created by the operation",
                        },
                    },
                },
            },
            "required": ["operation", "revision", "id_preservation", "id_map"],
        },
    },
}
