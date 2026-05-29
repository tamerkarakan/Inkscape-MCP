"""
Response normalizer: convert Inkscape CLI raw output to structured data.
"""
from __future__ import annotations

from typing import Any


def normalize_query_all(raw_stdout: str) -> list[dict[str, Any]]:
    """Parse --query-all output.

    Format: id,x,y,width,height (one object per line, px values).
    Returns [{id, x, y, width, height}] with raw px values
    (caller converts to user-unit via session.px_to_user).
    """
    results: list[dict[str, Any]] = []
    for line in raw_stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 5:
            results.append({
                "id": parts[0],
                "x": float(parts[1]),
                "y": float(parts[2]),
                "width": float(parts[3]),
                "height": float(parts[4]),
            })
    return results


def normalize_query_axis(raw_stdout: str) -> float | None:
    """Parse single-axis query output (--query-x, --query-y, etc.).

    Returns the float value or None if empty.
    """
    text = raw_stdout.strip()
    if not text:
        return None
    return float(text.splitlines()[-1].strip())


def normalize_export_result(
    output_path: str,
    file_size: int | None = None,
) -> dict[str, Any]:
    """Build structured result for an export operation."""
    result = {
        "output_path": output_path,
        "format": output_path.rsplit(".", 1)[-1].lower() if "." in output_path else "unknown",
    }
    if file_size is not None:
        result["file_size"] = file_size
    return result


def normalize_document_info(
    width: float,
    height: float,
    view_box: tuple[float, float, float, float],
    px_to_user_unit: float,
    revision: int,
) -> dict[str, Any]:
    """Build structured document info."""
    return {
        "width_px": width,
        "height_px": height,
        "viewBox": {
            "x": view_box[0],
            "y": view_box[1],
            "width": view_box[2],
            "height": view_box[3],
        },
        "px_to_user_unit": px_to_user_unit,
        "user_unit_to_px": 1.0 / px_to_user_unit if px_to_user_unit else 1.0,
        "revision": revision,
    }


def normalize_geometry_objects(
    raw_stdout: str,
    px_converter: callable = lambda v: v,
) -> dict[str, dict[str, Any]]:
    """Parse --query-all output and convert to user-unit dict keyed by id.

    px_converter: function that converts px → user-unit.
    """
    raw = normalize_query_all(raw_stdout)
    result: dict[str, dict[str, Any]] = {}
    for obj in raw:
        oid = obj["id"]
        result[oid] = {
            "x": px_converter(obj["x"]),
            "y": px_converter(obj["y"]),
            "width": px_converter(obj["width"]),
            "height": px_converter(obj["height"]),
        }
    return result
