"""
MCP Tool handler implementations.

Motor routing (Madde 12):
  - element_create / document_create → DOM (lxml, no Inkscape subprocess)
  - query / export / render_preview → Inkscape CLI
  - run_actions(path_op) → Inkscape CLI
  - element_update → DOM (not CLI)
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from lxml import etree
from pydantic import BaseModel, Field
from mcp.server.fastmcp import Image

from .actions import (
    chain_export_png,
    chain_export_svg,
    chain_path_difference,
    chain_path_exclusion,
    chain_path_intersection,
    chain_path_union,
    chain_set_attribute,
    chain_transform_translate,
)
from .exceptions import (
    IdDestroyedError,
    IdNotFoundError,
    InkscapeActionError,
    InkscapeError,
    InkscapeExportError,
    InkscapeNotFoundError,
    InkscapeProcessError,
    InkscapeTimeoutError,
    parse_stderr,
)
from .security import validate_action_arg
from .normalize import (
    normalize_document_info,
    normalize_export_result,
    normalize_geometry_objects,
)
from .security import SecurityConfig, validate_path
from .session import SessionManager, atomic_write_svg, read_svg_file

# SVG template for new documents
_SVG_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{width}" height="{height}"
     viewBox="0 0 {width} {height}">
  <defs id="defs1"/>
</svg>"""


# ── Tool result helpers ──


def _success(content: list[dict], structured: dict | None = None) -> dict:
    """Return the structured PAYLOAD directly (FastMCP wraps + validates it).

    FastMCP builds content + structuredContent from the returned payload and
    validates it against the tool's XxxStructured return annotation. The
    `content` arg is ignored (FastMCP auto-generates text content)."""
    return structured if structured is not None else {}


def _error(err: InkscapeError) -> dict:
    """Build an MCP isError result."""
    return {
        "content": [{"type": "text", "text": err.detail}],
        "isError": True,
        "structuredContent": err.to_dict(),
    }


# ── Inkscape CLI runner ──


async def _run_inkscape(
    args: list[str],
    config: SecurityConfig,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    """Run Inkscape CLI with timeout and child-kill.

    NEVER uses shell=True; args is always a list (security hard requirement).
    """
    binary = os.environ.get(
        "INKSCAPE_BIN",
        "inkscape.com" if os.name == "nt" else "inkscape",
    )
    timeout = timeout or config.default_timeout

    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            # Madde 7/10: kill child + tree
            try:
                proc.kill()
                if os.name == "nt":
                    # Windows: use taskkill for tree
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                    )
            except Exception:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
            raise InkscapeTimeoutError(
                f"Inkscape command timed out after {timeout}s: {args[:4]}..."
            )

        # Parse stderr for errors (F18: exit code unreliable)
        err = parse_stderr(stderr.decode("utf-8", errors="replace"))
        if err:
            raise err

        return subprocess.CompletedProcess(
            args=[binary] + args,
            returncode=proc.returncode,
            stdout=stdout.decode("utf-8", errors="replace").encode("utf-8"),
            stderr=stderr,
        )
    except FileNotFoundError:
        raise InkscapeNotFoundError(f"Inkscape binary not found at: {binary}")
    except InkscapeError:
        raise
    except Exception as exc:
        raise InkscapeProcessError(str(exc)) from exc


# ═══════════════════════════════════════════════════════
#  Tool handlers
# ═══════════════════════════════════════════════════════


# ── document_create (DOM) ──


async def tool_document_create(
    session_mgr: SessionManager,
    config: SecurityConfig,
    width: float = 200.0,
    height: float = 200.0,
    view_box: str | None = None,
    doc_name: str = "document",
) -> dict:
    """Create a new SVG document via DOM (no Inkscape CLI)."""
    workspace = config.workspace_root
    safe_name = "".join(c for c in doc_name if c.isalnum() or c in "._-")
    file_path = workspace / f"{safe_name}.svg"

    if view_box:
        vb_parts = view_box.split()
        vb_w = float(vb_parts[2])
        vb_h = float(vb_parts[3])
    else:
        vb_w, vb_h = width, height

    svg_content = _SVG_TEMPLATE.format(width=width, height=height)
    if view_box:
        svg_content = svg_content.replace(
            f'viewBox="0 0 {width} {height}"',
            f'viewBox="{view_box}"',
        )

    atomic_write_svg(file_path, svg_content, config)

    session_mgr.register_new(file_path, revision=1)

    return _success(
        [{"type": "text", "text": f"Document created: {file_path.name}"}],
        {
            "document_path": str(file_path),
            "file_name": file_path.name,
            "revision": 1,
            "width": width,
            "height": height,
            "viewBox": f"0 0 {vb_w} {vb_h}",
        },
    )


# ── element_create (DOM) ──


async def tool_element_create(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    element_type: str,
    properties: dict[str, Any],
    expected_revision: int | None = None,
    before_id: str | None = None,
) -> dict:
    """Create a new SVG element via DOM (F3/F4: NO Inkscape CLI for creation)."""
    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)

    async with state.lock:
        # Revision check
        session_mgr.check_revision(state, expected_revision)

        # Read and parse current SVG
        data = read_svg_file(state.svg_path, config)
        tree = etree.fromstring(data)

        # Generate unique ID (uuid4 — no collision within ~100s window)
        new_id = f"{element_type}_{uuid.uuid4().hex[:12]}"

        ns = "http://www.w3.org/2000/svg"

        if element_type == "rect":
            x = properties.get("x", 0)
            y = properties.get("y", 0)
            w = properties.get("width", 50)
            h = properties.get("height", 50)
            rx = properties.get("rx")
            ry = properties.get("ry")
            elem = etree.SubElement(tree, f"{{{ns}}}rect")
            elem.set("id", new_id)
            elem.set("x", str(x))
            elem.set("y", str(y))
            elem.set("width", str(w))
            elem.set("height", str(h))
            if rx is not None:
                elem.set("rx", str(rx))
            if ry is not None:
                elem.set("ry", str(ry))
            if "fill" in properties:
                elem.set("fill", str(properties["fill"]))
            if "stroke" in properties:
                elem.set("stroke", str(properties["stroke"]))
                if "stroke_width" in properties:
                    elem.set("stroke-width", str(properties["stroke_width"]))

        elif element_type == "circle":
            cx = properties.get("cx", 0)
            cy = properties.get("cy", 0)
            r = properties.get("r", 20)
            elem = etree.SubElement(tree, f"{{{ns}}}circle")
            elem.set("id", new_id)
            elem.set("cx", str(cx))
            elem.set("cy", str(cy))
            elem.set("r", str(r))
            if "fill" in properties:
                elem.set("fill", str(properties["fill"]))
            if "stroke" in properties:
                elem.set("stroke", str(properties["stroke"]))
                if "stroke_width" in properties:
                    elem.set("stroke-width", str(properties["stroke_width"]))

        elif element_type == "path":
            d = properties.get("d", "")
            elem = etree.SubElement(tree, f"{{{ns}}}path")
            elem.set("id", new_id)
            elem.set("d", str(d))
            if "fill" in properties:
                elem.set("fill", str(properties["fill"]))
            if "stroke" in properties:
                elem.set("stroke", str(properties["stroke"]))
                if "stroke_width" in properties:
                    elem.set("stroke-width", str(properties["stroke_width"]))

        elif element_type == "text":
            x = properties.get("x", 0)
            y = properties.get("y", 0)
            text = properties.get("text", "")
            elem = etree.SubElement(tree, f"{{{ns}}}text")
            elem.set("id", new_id)
            elem.set("x", str(x))
            elem.set("y", str(y))
            if "font_family" in properties:
                elem.set("font-family", str(properties["font_family"]))
            if "font_size" in properties:
                elem.set("font-size", str(properties["font_size"]))
            if "fill" in properties:
                elem.set("fill", str(properties["fill"]))
            elem.text = str(text)

        elif element_type == "ellipse":
            elem = etree.SubElement(tree, f"{{{ns}}}ellipse")
            elem.set("id", new_id)
            elem.set("cx", str(properties.get("cx", 0)))
            elem.set("cy", str(properties.get("cy", 0)))
            elem.set("rx", str(properties.get("rx", 30)))
            elem.set("ry", str(properties.get("ry", 20)))

        else:
            raise InkscapeError(f"Unsupported element_type: {element_type}")

        # Generic attribute pass-through (fixes silent attribute dropping):
        # apply any property the type-branch above did NOT already set —
        # hyphenated names and extra styles (font-size, stroke-width,
        # stroke-linecap, letter-spacing, text-anchor, font-weight, opacity,
        # transform, ...). Only fills gaps; never overrides branch output.
        # Weak/low-context clients rely on element_create alone, so nothing
        # passed must be silently dropped.
        _passthrough_map = {
            "stroke_width": "stroke-width",
            "font_family": "font-family",
            "font_size": "font-size",
        }
        for _k, _v in properties.items():
            if _k in ("id", "text"):
                continue
            _attr = _passthrough_map.get(_k, _k)
            if elem.get(_attr) is None:
                elem.set(_attr, str(_v))

        # z-order: optionally insert directly BEFORE an existing element
        # (otherwise the new element stays appended at the end = top z-order).
        # Lets a client place e.g. a shadow under an already-created shape.
        if before_id:
            _t = tree.xpath(f"//*[@id='{before_id}']")
            if _t:
                _t[0].addprevious(elem)

        # Serialize and atomically write
        new_svg = etree.tostring(
            tree,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )
        atomic_write_svg(state.svg_path, new_svg, config)

        # Update revision
        new_rev = session_mgr.increment_revision(state)

        # Compute px-equivalent coordinates (F5: user-unit → px for reference)
        px_coords = {}
        for coord_key in ("x", "y", "cx", "cy", "r", "width", "height"):
            if coord_key in properties:
                px_coords[coord_key] = session_mgr.user_to_px(
                    state, float(properties[coord_key])
                )

    return _success(
        [{"type": "text", "text": f"{element_type} created with id '{new_id}'"}],
        {
            "element_id": new_id,
            "element_type": element_type,
            "revision": new_rev,
            "px_coords": px_coords,
        },
    )


# ── element_update (DOM) ──


async def tool_element_update(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    object_id: str,
    properties: dict[str, Any],
    expected_revision: int | None = None,
) -> dict:
    """Update properties of an existing SVG element via DOM (Madde 12)."""
    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)

    async with state.lock:
        # Revision check
        session_mgr.check_revision(state, expected_revision)

        # Check if ID was destroyed (Madde 14: silinmiş id ≠ stale revision)
        if object_id in state.destroyed_ids:
            raise IdDestroyedError(object_id)

        # Read and parse current SVG
        data = read_svg_file(state.svg_path, config)
        tree = etree.fromstring(data)

        # Find element by id
        found = tree.xpath(f"//*[@id='{object_id}']")
        if not found:
            raise IdNotFoundError(object_id)

        elem = found[0]

        # Apply property updates
        for prop_name, prop_value in properties.items():
            # Map Python snake_case names to SVG attribute names
            attr_map = {
                "x": "x",
                "y": "y",
                "width": "width",
                "height": "height",
                "cx": "cx",
                "cy": "cy",
                "r": "r",
                "rx": "rx",
                "ry": "ry",
                "d": "d",
                "fill": "fill",
                "stroke": "stroke",
                "stroke_width": "stroke-width",
                "font_family": "font-family",
                "font_size": "font-size",
                "text": None,  # Text content, not attribute
                "opacity": "opacity",
                "transform": "transform",
            }
            svg_attr = attr_map.get(prop_name)
            if svg_attr is None and prop_name == "text":
                elem.text = str(prop_value)
            elif svg_attr is not None:
                elem.set(svg_attr, str(prop_value))
            else:
                # Allow raw SVG attribute names as pass-through
                elem.set(prop_name, str(prop_value))

        # Serialize and atomically write
        new_svg = etree.tostring(
            tree,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )
        atomic_write_svg(state.svg_path, new_svg, config)

        # Update revision
        new_rev = session_mgr.increment_revision(state)

    return _success(
        [{"type": "text", "text": f"Updated {object_id} ({len(properties)} properties)"}],
        {
            "object_id": object_id,
            "revision": new_rev,
            "updated_properties": list(properties.keys()),
        },
    )


# ── query (Inkscape CLI) ──


async def tool_query(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    object_ids: list[str] | None = None,
) -> dict:
    """Query object geometries via Inkscape CLI.

    Returns user-unit coordinates (Madde 15/F5: px→user-unit conversion).
    """
    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)

    async with state.lock:
        # Reload unit info from disk (file is authority, Madde 1)
        session_mgr._load_unit_info(state)

        if object_ids and len(object_ids) > 0:
            # Query specific objects using --query-id + --query-all
            id_args = [f"--query-id={','.join(object_ids)}"]
            result = await _run_inkscape(
                ["--query-all", *id_args, str(state.svg_path)],
                config,
            )
        else:
            result = await _run_inkscape(
                ["--query-all", str(state.svg_path)],
                config,
            )

        stdout = result.stdout.decode("utf-8", errors="replace")

        # Convert px → user-unit
        px_to_uu = state.px_to_user_unit

        def converter(v: float) -> float:
            return v / px_to_uu if px_to_uu else v

        objects = normalize_geometry_objects(stdout, converter)

        # Build document info
        doc_info = normalize_document_info(
            state.width_px,
            state.height_px,
            state.view_box,
            state.px_to_user_unit,
            state.revision,
        )

    return _success(
        [{"type": "text", "text": f"Queried {len(objects)} objects"}],
        {
            "revision": state.revision,
            "objects": objects,
            "document": doc_info,
        },
    )


# ── export (Inkscape CLI) ──


async def tool_export(
    session_mgr: SessionManager,
    config: SecurityConfig,
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
    """Export SVG to PNG, SVG, PDF, etc. via Inkscape CLI."""
    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)

    # Validate format
    if export_format not in config.allowed_export_formats:
        raise InkscapeExportError(
            f"Unsupported export format: {export_format}. "
            f"Allowed: {config.allowed_export_formats}"
        )

    # Build output path (server generates, Madde 8)
    safe_name = "".join(c for c in output_name if c.isalnum() or c in "._-")
    # Avoid double extension if output_name already ends with .<format>
    if safe_name.lower().endswith("." + export_format.lower()):
        safe_name = safe_name[: -(len(export_format) + 1)]
    output_path = config.workspace_root / f"{safe_name}.{export_format}"

    async with state.lock:
        session_mgr.check_revision(state, expected_revision)

        if export_format == "png":
            actions = chain_export_png(
                output_path, dpi=dpi, width=width, height=height,
                background=background,
            )
            args = ["--actions=" + ";".join(
                f"{name}:{arg}" if arg else name for name, arg in actions
            )]
        elif export_format == "svg":
            actions = chain_export_svg(output_path, plain=plain_svg)
            args = ["--actions=" + ";".join(
                f"{name}:{arg}" if arg else name for name, arg in actions
            )]
        else:
            # Generic export via --export-type / --export-filename
            args = [
                f"--export-filename={output_path}",
                f"--export-type={export_format}",
            ]

        if object_ids:
            args.insert(0, f"--export-id={';'.join(object_ids)}")

        args.append(str(state.svg_path))

        await _run_inkscape(args, config, timeout=config.export_timeout)

    # Check output
    if not output_path.exists():
        raise InkscapeExportError(
            f"Export produced no output file: {output_path}"
        )

    file_size = output_path.stat().st_size
    export_norm = normalize_export_result(str(output_path), file_size)

    return _success(
        [{"type": "text", "text": f"Exported to {output_path.name} ({file_size} bytes)"}],
        export_norm,
    )


# ── render_preview (Inkscape CLI) ──


async def _render_preview_png(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    width: int = 400,
    height: int | None = None,
) -> tuple[bytes, int]:
    """Render the current SVG to PNG bytes. Returns (png_bytes, revision).

    Shared core used by both the render_preview tool and the preview resource.
    """
    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)

    async with state.lock:
        # Reload unit info
        session_mgr._load_unit_info(state)

        with tempfile.NamedTemporaryFile(
            suffix=".png", dir=str(config.workspace_root), delete=False
        ) as tmp:
            tmp_png = Path(tmp.name)

        try:
            actions = chain_export_png(tmp_png, width=width, height=height)
            action_str = ";".join(
                f"{name}:{arg}" if arg else name for name, arg in actions
            )
            await _run_inkscape(
                ["--actions=" + action_str, str(state.svg_path)],
                config,
                timeout=config.export_timeout,
            )

            png_data = tmp_png.read_bytes()
            return png_data, state.revision
        finally:
            try:
                tmp_png.unlink(missing_ok=True)
            except OSError:
                pass


async def tool_render_preview(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    width: int = 400,
    height: int | None = None,
) -> Image:
    """Render a PNG preview of the current SVG and return it as an inline image.

    Returns a FastMCP Image so the client actually RECEIVES the PNG. (The prior
    `_success`-based path returned only structured metadata and silently dropped
    the image content — broken for the tool's whole purpose.)
    """
    png_data, _revision = await _render_preview_png(
        session_mgr, config, document_path, width=width, height=height
    )
    return Image(data=png_data, format="png")


# ── run_actions (Inkscape CLI escape hatch) ──


def _apply_transform_translate_dom(
    svg_bytes: bytes,
    object_id: str,
    dx: float,
    dy: float,
) -> bytes:
    """Apply translate to an element's x/y attributes via DOM (lxml).

    Madde 12: DOM baseline — bakes dx/dy into x/y attributes directly.
    Inkscape CLI transform-translate is kept for verification / advanced ops.

    Returns modified SVG bytes.
    """
    tree = etree.fromstring(svg_bytes)
    found = tree.xpath(f"//*[@id='{object_id}']")
    if not found:
        raise IdNotFoundError(object_id)

    elem = found[0]

    # Bake translation into x and y attributes
    for attr in ("x", "y", "cx", "cy"):
        val = elem.get(attr)
        if val is not None:
            try:
                new_val = float(val) + (dx if attr in ("x", "cx") else dy)
                elem.set(attr, str(new_val))
            except ValueError:
                pass

    # If element has no position attributes, add a transform attribute as fallback
    has_pos = any(elem.get(a) is not None for a in ("x", "y", "cx", "cy"))
    if not has_pos:
        existing_transform = elem.get("transform", "")
        translate_str = f"translate({dx},{dy})"
        if existing_transform:
            elem.set("transform", f"{existing_transform} {translate_str}")
        else:
            elem.set("transform", translate_str)

    return etree.tostring(
        tree,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    )


async def tool_run_actions(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    operation: str,
    object_ids: list[str],
    action_params: dict[str, Any] | None = None,
    expected_revision: int | None = None,
    ctx=None,
) -> dict:
    """Run a headless-safe Inkscape action on a document.

    Supports path_op operations (union, difference, intersection, exclusion).
    Returns id-map for id-changing operations (Madde 14/F8).
    """
    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)

    allowed_ops = {"path_union", "path_difference", "path_intersection",
                   "path_exclusion", "set_attribute", "transform_translate"}

    if operation not in allowed_ops:
        raise InkscapeActionError(operation, f"Unknown operation: {operation}")

    # ── P0-2: Argüman enjeksiyonu koruması ──
    # object_ids ve action_params kullanıcı girdisi — ; ve : karakterleri
    # action zinciri enjeksiyonuna yol açar. validate_action_arg ile reddet.
    for oid in object_ids:
        validate_action_arg(oid)
    if action_params:
        for key, val in action_params.items():
            validate_action_arg(key)
            validate_action_arg(str(val))

    # Destructive-op confirmation gate (MCP elicitation)
    destructive_ops = {"path_union", "path_difference", "path_intersection",
                       "path_exclusion"}
    if operation in destructive_ops:
        confirmed = await _confirm_destructive(
            ctx, config, f"{operation} on {', '.join(object_ids)}"
        )
        if not confirmed:
            raise InkscapeActionError(operation, "destructive operation not confirmed by user")

    async with state.lock:
        session_mgr.check_revision(state, expected_revision)

        # Check if any target ID was destroyed (Madde 14: silinmiş-id kontrolü)
        for oid in object_ids:
            if oid in state.destroyed_ids:
                raise IdDestroyedError(oid, operation)

        # Collect IDs before operation
        data = read_svg_file(state.svg_path, config)
        tree_before = etree.fromstring(data)
        ids_before = session_mgr.collect_ids(tree_before)

        if operation == "path_union":
            actions = chain_path_union(*object_ids)
        elif operation == "path_difference":
            actions = chain_path_difference(*object_ids)
        elif operation == "path_intersection":
            actions = chain_path_intersection(*object_ids)
        elif operation == "path_exclusion":
            actions = chain_path_exclusion(*object_ids)
        elif operation == "set_attribute":
            if not action_params:
                raise InkscapeActionError("set_attribute", "action_params required")
            attr = action_params.get("attribute", "")
            value = action_params.get("value", "")
            actions = chain_set_attribute(object_ids[0], attr, value)
        elif operation == "transform_translate":
            if not action_params:
                raise InkscapeActionError("transform_translate", "action_params required")
            dx = float(action_params.get("dx", 0))
            dy = float(action_params.get("dy", 0))

            # Madde 12: DOM baseline — bake x/y via lxml, no CLI
            data_after = _apply_transform_translate_dom(data, object_ids[0], dx, dy)
            atomic_write_svg(state.svg_path, data_after, config)

            # Collect IDs after (same IDs, just moved)
            tree_after = etree.fromstring(data_after)
            ids_after = session_mgr.collect_ids(tree_after)
            id_map = session_mgr.diff_ids(ids_before, ids_after)

            # Update revision
            new_rev = session_mgr.increment_revision(state)

            structured = {
                "operation": operation,
                "revision": new_rev,
                "id_preservation": "preserving",
                "id_map": id_map,
                "dx": dx,
                "dy": dy,
            }

            return _success(
                [{"type": "text", "text": f"Operation '{operation}' completed via DOM (dx={dx}, dy={dy}). revision={new_rev}"}],
                structured,
            )
        else:
            actions = []

        # Build actions string with export to temp, then atomically replace
        # --actions doesn't write back to input file (F19); must export
        import tempfile as tmpmod
        fd, tmp_name = tmpmod.mkstemp(
            dir=str(state.svg_path.parent),
            prefix=".inkscape_tmp_", suffix=".svg"
        )
        os.close(fd)
        tmp_path = Path(tmp_name)

        try:
            # Append export chain to actions
            export_actions = [
                ("export-filename", str(tmp_path)),
                ("export-type", "svg"),
                ("export-do", None),
            ]
            all_actions = list(actions) + export_actions

            action_str = ";".join(
                f"{name}:{arg}" if arg else name for name, arg in all_actions
            )
            await _run_inkscape(
                ["--actions=" + action_str, str(state.svg_path)],
                config,
                timeout=config.export_timeout,
            )

            # Verify export succeeded
            if not tmp_path.exists():
                raise InkscapeActionError(operation, "Export produced no output")

            # Atomically replace the original SVG with the modified result
            data_after = tmp_path.read_bytes()
            atomic_write_svg(state.svg_path, data_after, config)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

        # Collect IDs after operation
        tree_after = etree.fromstring(data_after)
        ids_after = session_mgr.collect_ids(tree_after)

        # Compute id-map
        id_map = session_mgr.diff_ids(ids_before, ids_after)

        # Track destroyed IDs
        state.destroyed_ids.update(id_map["destroyed"])

        # Update revision
        new_rev = session_mgr.increment_revision(state)

        # Determine if id-changing
        is_id_changing = len(id_map["destroyed"]) > 0 or len(id_map["created"]) > 0
        id_preservation = "changing" if is_id_changing else "preserving"

        structured = {
            "operation": operation,
            "revision": new_rev,
            "id_preservation": id_preservation,
            "id_map": id_map,
        }

        return _success(
            [{"type": "text", "text": f"Operation '{operation}' completed. "
                                      f"revision={new_rev}"}],
            structured,
        )


# ═══════════════════════════════════════════════════════
#  GUI tool handlers (live --active-window driver)
# ═══════════════════════════════════════════════════════
#
#  gui_open / gui_apply / gui_export / gui_close drive a VISIBLE Inkscape
#  window via GuiSessionManager. Unlike the headless tools above, edits act on
#  the in-memory document of the live window (no file write-back, no id_map).


def _gui_app_id(document_path: str) -> str:
    """Deterministic --app-id-tag per document, so reopening reuses the window."""
    stem = Path(document_path).stem
    safe = "".join(c for c in stem if c.isalnum() or c in "._-")
    return f"inkmcp-{safe or 'doc'}"


# GUI-safe live operations (CLI actions injected into the active window).
# transform_translate is DOM-only (writes the file) → excluded here.
_GUI_ALLOWED_OPS = {
    "path_union",
    "path_difference",
    "path_intersection",
    "path_exclusion",
    "set_attribute",
}


async def tool_gui_open(
    gui_mgr,
    config: SecurityConfig,
    document_path: str,
) -> dict:
    """Open (or reuse) a visible Inkscape GUI window for the document."""
    svg_path = validate_path(Path(document_path), config)
    app_id = _gui_app_id(document_path)
    await gui_mgr.get_or_start(app_id, svg_path)
    return _success(
        [{"type": "text", "text": f"GUI window open for {svg_path.name} ({app_id})"}],
        {
            "app_id": app_id,
            "document_path": str(svg_path),
            "status": "open",
        },
    )


async def tool_gui_apply(
    gui_mgr,
    config: SecurityConfig,
    document_path: str,
    operation: str,
    object_ids: list[str],
    action_params: dict[str, Any] | None = None,
) -> dict:
    """Apply a headless-safe action to the live GUI window (in-memory edit)."""
    svg_path = validate_path(Path(document_path), config)
    app_id = _gui_app_id(document_path)

    if operation not in _GUI_ALLOWED_OPS:
        raise InkscapeActionError(operation, f"Unknown GUI operation: {operation}")

    # P0-2: argüman enjeksiyonu koruması (run_actions ile aynı kapı).
    for oid in object_ids:
        validate_action_arg(oid)
    if action_params:
        for key, val in action_params.items():
            validate_action_arg(key)
            validate_action_arg(str(val))

    session = await gui_mgr.get_or_start(app_id, svg_path)

    if operation == "path_union":
        actions = chain_path_union(*object_ids)
    elif operation == "path_difference":
        actions = chain_path_difference(*object_ids)
    elif operation == "path_intersection":
        actions = chain_path_intersection(*object_ids)
    elif operation == "path_exclusion":
        actions = chain_path_exclusion(*object_ids)
    elif operation == "set_attribute":
        if not action_params:
            raise InkscapeActionError("set_attribute", "action_params required")
        attr = action_params.get("attribute", "")
        value = action_params.get("value", "")
        actions = chain_set_attribute(object_ids[0], attr, value)
    else:  # pragma: no cover - guarded by _GUI_ALLOWED_OPS
        actions = []

    action_str = ";".join(
        f"{name}:{arg}" if arg else name for name, arg in actions
    )
    await session.run_actions(action_str)

    return _success(
        [{"type": "text", "text": f"Applied '{operation}' to live window {app_id}"}],
        {
            "app_id": app_id,
            "operation": operation,
            "status": "applied",
        },
    )


async def tool_gui_export(
    gui_mgr,
    config: SecurityConfig,
    document_path: str,
    output_name: str,
    export_format: str = "svg",
) -> dict:
    """Export the CURRENT live-window state to a file (server-generated path)."""
    svg_path = validate_path(Path(document_path), config)
    app_id = _gui_app_id(document_path)

    if export_format not in config.allowed_export_formats:
        raise InkscapeExportError(
            f"Unsupported export format: {export_format}. "
            f"Allowed: {config.allowed_export_formats}"
        )

    safe_name = "".join(c for c in output_name if c.isalnum() or c in "._-")
    # Avoid double extension if output_name already ends with .<format>
    if safe_name.lower().endswith("." + export_format.lower()):
        safe_name = safe_name[: -(len(export_format) + 1)]
    output_path = config.workspace_root / f"{safe_name}.{export_format}"

    session = await gui_mgr.get_or_start(app_id, svg_path)
    await session.export_live(output_path, export_format)

    if not output_path.exists():
        raise InkscapeExportError(
            f"Live export produced no output file: {output_path}"
        )

    file_size = output_path.stat().st_size
    return _success(
        [{"type": "text", "text": f"Live-exported to {output_path.name} ({file_size} bytes)"}],
        {
            "output_path": str(output_path),
            "format": export_format,
            "file_size": file_size,
        },
    )


async def tool_gui_close(
    gui_mgr,
    config: SecurityConfig,
    document_path: str,
) -> dict:
    """Close the live GUI window for the document (terminate the session)."""
    app_id = _gui_app_id(document_path)
    closed = await gui_mgr.close(app_id)
    return _success(
        [{"type": "text", "text": f"GUI window {app_id} {'closed' if closed else 'was not open'}"}],
        {
            "app_id": app_id,
            "status": "closed" if closed else "not_open",
        },
    )


# ═══════════════════════════════════════════════════════
#  Image tools (raster import + trace-bitmap fallback)
# ═══════════════════════════════════════════════════════


async def tool_import_image(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    image_path: str,
    x: float = 0.0,
    y: float = 0.0,
    width: float | None = None,
    height: float | None = None,
    expected_revision: int | None = None,
) -> dict:
    """Embed a raster (PNG/JPG/GIF/WEBP) into the SVG as <image> via DOM."""
    import base64
    svg_path = validate_path(Path(document_path), config)
    img_path = validate_path(Path(image_path), config)
    if not img_path.exists():
        raise InkscapeError(f"Image file not found: {img_path}")
    suffix = img_path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_map.get(suffix)
    if mime is None:
        raise InkscapeError(f"Unsupported image type: {suffix}")
    if width is None:
        width = 100.0
    if height is None:
        height = 100.0
    img_bytes = img_path.read_bytes()
    b64 = base64.b64encode(img_bytes).decode("ascii")
    data_uri = f"data:{mime};base64,{b64}"
    state = await session_mgr.get_or_open(svg_path)
    async with state.lock:
        session_mgr.check_revision(state, expected_revision)
        data = read_svg_file(state.svg_path, config)
        tree = etree.fromstring(data)
        new_id = f"image_{uuid.uuid4().hex[:12]}"
        ns = "http://www.w3.org/2000/svg"
        elem = etree.SubElement(tree, f"{{{ns}}}image")
        elem.set("id", new_id)
        elem.set("x", str(x))
        elem.set("y", str(y))
        elem.set("width", str(width))
        elem.set("height", str(height))
        xlink_ns = "http://www.w3.org/1999/xlink"
        elem.set(f"{{{xlink_ns}}}href", data_uri)
        new_svg = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", pretty_print=True)
        atomic_write_svg(state.svg_path, new_svg, config)
        new_rev = session_mgr.increment_revision(state)
    return _success(
        [{"type": "text", "text": f"Image embedded with id '{new_id}'"}],
        {"element_id": new_id, "element_type": "image", "revision": new_rev, "width": float(width), "height": float(height)},
    )


async def tool_trace_bitmap(
    session_mgr: SessionManager,
    config: SecurityConfig,
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
    ctx=None,
) -> dict:
    """Trace an embedded <image> into <path> geometry (Inkscape object-trace)."""
    svg_path = validate_path(Path(document_path), config)
    validate_action_arg(image_id)
    confirmed = await _confirm_destructive(ctx, config, f"trace_bitmap on {image_id}")
    if not confirmed:
        raise InkscapeActionError("trace_bitmap", "destructive operation not confirmed by user")
    state = await session_mgr.get_or_open(svg_path)
    async with state.lock:
        session_mgr.check_revision(state, expected_revision)

        data = read_svg_file(state.svg_path, config)
        tree_before = etree.fromstring(data)
        ids_before = session_mgr.collect_ids(tree_before)

        trace_args = f"{int(scans)},{int(bool(smooth))},{int(bool(stack))},{int(bool(remove_background))},{int(speckles)},{float(smooth_corners)},{int(bool(optimize))}"
        actions = [("select-by-id", image_id), ("object-trace", trace_args)]

        import tempfile as tmpmod
        fd, tmp_name = tmpmod.mkstemp(dir=str(state.svg_path.parent), prefix=".inkscape_tmp_", suffix=".svg")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            export_actions = [("export-filename", str(tmp_path)), ("export-type", "svg"), ("export-do", None)]
            all_actions = list(actions) + export_actions
            action_str = ";".join(f"{name}:{arg}" if arg else name for name, arg in all_actions)
            await _run_inkscape(["--actions=" + action_str, str(state.svg_path)], config, timeout=config.export_timeout)
            if not tmp_path.exists():
                raise InkscapeActionError("trace_bitmap", "Export produced no output")
            data_after = tmp_path.read_bytes()
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        tree_after = etree.fromstring(data_after)
        ids_after = session_mgr.collect_ids(tree_after)
        id_map = session_mgr.diff_ids(ids_before, ids_after)

        if not id_map["created"]:
            raise InkscapeActionError("trace_bitmap", "produced no geometry (check image_id or trace params)")

        if remove_source:
            tree_after = etree.fromstring(data_after)
            found = tree_after.xpath(f"//*[@id='{image_id}']")
            if found:
                el = found[0]
                el.getparent().remove(el)
                data_after = etree.tostring(tree_after, xml_declaration=True, encoding="UTF-8", pretty_print=True)
                tree_after = etree.fromstring(data_after)
                ids_after = session_mgr.collect_ids(tree_after)
                id_map = session_mgr.diff_ids(ids_before, ids_after)

        atomic_write_svg(state.svg_path, data_after, config)
        state.destroyed_ids.update(id_map["destroyed"])
        new_rev = session_mgr.increment_revision(state)
        id_preservation = "changing" if (id_map["destroyed"] or id_map["created"]) else "preserving"
        return _success(
            [{"type": "text", "text": f"trace_bitmap on '{image_id}': created {len(id_map['created'])} path(s). revision={new_rev}"}],
            {"operation": "trace_bitmap", "revision": new_rev, "image_id": image_id, "id_preservation": id_preservation, "id_map": id_map}
        )


# ═══════════════════════════════════════════════════════
#  Interaction tools (MCP elicitation — ask the human)
# ═══════════════════════════════════════════════════════


class _AskResponse(BaseModel):
    response: str = Field(default="", description="The user's free-text answer")


class _ConfirmResponse(BaseModel):
    confirm: bool = Field(default=False, description="Confirm the destructive operation")


async def _confirm_destructive(ctx, config, description: str) -> bool:
    """Gate: user must confirm a destructive operation via MCP elicitation.

    Policy: no ctx (direct/test) → proceed; confirmation disabled → proceed;
    client lacks elicitation (elicit raises) → proceed (backward-compatible);
    accept → honor data.confirm; decline/cancel → block.
    """
    if ctx is None:
        return True
    if not config.require_confirmation_for_destructive:
        return True
    try:
        result = await ctx.elicit(
            f"Confirm destructive operation: {description}",
            _ConfirmResponse,
        )
    except Exception:
        return True
    if result.action == "accept":
        return bool(result.data.confirm)
    return False


async def tool_ask_user(ctx, question: str, options: list[str] | None = None) -> dict:
    """Ask the human (behind the client) a structured question via elicitation."""
    if ctx is None:
        return _success(
            [{"type": "text", "text": f"ask_user: {question[:60]}"}],
            {"answered": False, "action": "unsupported", "response": ""},
        )

    message = question
    if options and len(options) > 0:
        message += "\nOptions: " + ", ".join(options)

    try:
        result = await ctx.elicit(message=message, schema=_AskResponse)
    except Exception:
        return _success(
            [{"type": "text", "text": f"ask_user: {question[:60]}"}],
            {"answered": False, "action": "unsupported", "response": ""},
        )

    if result.action == "accept":
        resp = getattr(result.data, "response", "")
        return _success(
            [{"type": "text", "text": f"ask_user: {question[:60]}"}],
            {"answered": True, "action": "accept", "response": resp},
        )
    elif result.action == "decline":
        return _success(
            [{"type": "text", "text": f"ask_user: {question[:60]}"}],
            {"answered": False, "action": "decline", "response": ""},
        )
    else:
        return _success(
            [{"type": "text", "text": f"ask_user: {question[:60]}"}],
            {"answered": False, "action": "cancel", "response": ""},
        )


def tool_workspace_info(config) -> dict:
    """Report the MCP working directory (where to place inputs / find outputs)."""
    ws = config.workspace_root
    try:
        files = sorted([p.name for p in ws.iterdir() if p.is_file()])[:100]
    except Exception:
        files = []
    note = (
        "This is the MCP's working directory. Put any input images you want to "
        "import/trace HERE, and all generated files (exports, previews) are saved "
        "HERE. Use absolute paths under this directory."
    )
    return _success(
        [{"type": "text", "text": f"workspace: {ws}"}],
        {"workspace_path": str(ws), "files": files, "note": note},
    )


async def tool_write_svg(
    session_mgr: SessionManager,
    config: SecurityConfig,
    doc_name: str,
    svg_content: str,
) -> dict:
    """Author a full SVG in one call (validated well-formed XML, saved to workspace)."""
    workspace = config.workspace_root
    safe_name = "".join(c for c in doc_name if c.isalnum() or c in "._-")
    file_path = workspace / f"{safe_name}.svg"

    try:
        etree.fromstring(svg_content.encode("utf-8"))
    except Exception as exc:
        raise InkscapeError(f"Invalid SVG XML: {exc}")

    atomic_write_svg(file_path, svg_content, config)
    session_mgr.register_new(file_path, revision=1)

    return _success(
        [{"type": "text", "text": f"SVG written: {file_path.name}"}],
        {"document_path": str(file_path), "file_name": file_path.name, "revision": 1},
    )


# ═══════════════════════════════════════════════════════
#  Transform + z-order (DOM)
# ═══════════════════════════════════════════════════════


async def tool_transform_element(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    object_id: str,
    operation: str,
    params: dict[str, Any] | None = None,
    expected_revision: int | None = None,
) -> dict:
    """Apply translate/scale/rotate/skew to an element (composes its transform)."""
    params = params or {}
    if operation == "translate":
        t = f"translate({float(params.get('dx',0))},{float(params.get('dy',0))})"
    elif operation == "scale":
        sx = float(params.get('sx', 1))
        sy = float(params.get('sy', sx))
        t = f"scale({sx},{sy})"
    elif operation == "rotate":
        angle = float(params.get('angle', 0))
        if 'cx' in params and 'cy' in params:
            t = f"rotate({angle} {float(params['cx'])} {float(params['cy'])})"
        else:
            t = f"rotate({angle})"
    elif operation == "skew_x":
        t = f"skewX({float(params.get('angle',0))})"
    elif operation == "skew_y":
        t = f"skewY({float(params.get('angle',0))})"
    else:
        raise InkscapeError(f"Unknown transform operation: {operation}")

    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)
    async with state.lock:
        session_mgr.check_revision(state, expected_revision)
        if object_id in state.destroyed_ids:
            raise IdDestroyedError(object_id)
        data = read_svg_file(state.svg_path, config)
        tree = etree.fromstring(data)
        found = tree.xpath(f"//*[@id='{object_id}']")
        if not found:
            raise IdNotFoundError(object_id)
        elem = found[0]
        existing = elem.get("transform", "").strip()
        combined = (existing + " " + t).strip() if existing else t
        elem.set("transform", combined)
        new_svg = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", pretty_print=True)
        atomic_write_svg(state.svg_path, new_svg, config)
        new_rev = session_mgr.increment_revision(state)
    return _success(
        [{"type": "text", "text": f"transform {operation} on {object_id}"}],
        {"object_id": object_id, "revision": new_rev, "transform": combined},
    )


async def tool_reorder_element(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    object_id: str,
    position: str,
    expected_revision: int | None = None,
) -> dict:
    """Change an element's z-order: top | bottom | up | down (DOM reposition)."""
    if position not in {"top", "bottom", "up", "down"}:
        raise InkscapeError(f"Unknown position: {position}")

    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)
    async with state.lock:
        session_mgr.check_revision(state, expected_revision)
        if object_id in state.destroyed_ids:
            raise IdDestroyedError(object_id)
        data = read_svg_file(state.svg_path, config)
        tree = etree.fromstring(data)
        found = tree.xpath(f"//*[@id='{object_id}']")
        if not found:
            raise IdNotFoundError(object_id)
        elem = found[0]
        parent = elem.getparent()
        if parent is None:
            raise InkscapeError("element has no parent")

        if position == "top":
            parent.append(elem)
        elif position == "bottom":
            parent.insert(0, elem)
        elif position == "up":
            nxt = elem.getnext()
            if nxt is not None:
                nxt.addnext(elem)
        elif position == "down":
            prv = elem.getprevious()
            if prv is not None:
                prv.addprevious(elem)

        new_svg = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", pretty_print=True)
        atomic_write_svg(state.svg_path, new_svg, config)
        new_rev = session_mgr.increment_revision(state)
    return _success(
        [{"type": "text", "text": f"moved {object_id} {position}"}],
        {"object_id": object_id, "revision": new_rev, "position": position},
    )


# ═══════════════════════════════════════════════════════
#  Paint: gradients + patterns (DOM, into <defs>)
# ═══════════════════════════════════════════════════════


async def tool_create_gradient(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    gradient_type: str,
    stops: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
    expected_revision: int | None = None,
) -> dict:
    """Define a linear/radial gradient in <defs>; returns an id for fill='url(#id)'."""
    params = params or {}
    if gradient_type not in {"linear", "radial"}:
        raise InkscapeError(f"Unknown gradient_type: {gradient_type}")

    ns = "http://www.w3.org/2000/svg"
    grad_id = f"grad_{uuid.uuid4().hex[:12]}"

    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)
    async with state.lock:
        session_mgr.check_revision(state, expected_revision)
        data = read_svg_file(state.svg_path, config)
        tree = etree.fromstring(data)
        defs = tree.find(f"{{{ns}}}defs")
        if defs is None:
            defs = etree.Element(f"{{{ns}}}defs")
            tree.insert(0, defs)

        if gradient_type == "linear":
            g = etree.SubElement(defs, f"{{{ns}}}linearGradient")
            g.set("id", grad_id)
            g.set("gradientUnits", "userSpaceOnUse")
            g.set("x1", str(params.get("x1", 0)))
            g.set("y1", str(params.get("y1", 0)))
            g.set("x2", str(params.get("x2", 1)))
            g.set("y2", str(params.get("y2", 0)))
        else:  # radial
            g = etree.SubElement(defs, f"{{{ns}}}radialGradient")
            g.set("id", grad_id)
            g.set("gradientUnits", "userSpaceOnUse")
            g.set("cx", str(params.get("cx", 0)))
            g.set("cy", str(params.get("cy", 0)))
            g.set("r", str(params.get("r", 1)))
            if "fx" in params and "fy" in params:
                g.set("fx", str(params["fx"]))
                g.set("fy", str(params["fy"]))

        for stop in stops:
            s = etree.SubElement(g, f"{{{ns}}}stop")
            s.set("offset", str(stop.get("offset", 0)))
            s.set("stop-color", str(stop.get("color", "#000000")))
            if "opacity" in stop:
                s.set("stop-opacity", str(stop["opacity"]))

        new_svg = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", pretty_print=True)
        atomic_write_svg(state.svg_path, new_svg, config)
        new_rev = session_mgr.increment_revision(state)

    return _success(
        [{"type": "text", "text": f"{gradient_type} gradient {grad_id}"}],
        {"gradient_id": grad_id, "gradient_type": gradient_type, "revision": new_rev},
    )


async def tool_create_pattern(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    width: float,
    height: float,
    content_svg: str,
    expected_revision: int | None = None,
) -> dict:
    """Define a tile <pattern> in <defs>; returns an id for fill='url(#id)'."""
    ns = "http://www.w3.org/2000/svg"
    pat_id = f"pat_{uuid.uuid4().hex[:12]}"

    svg_path = validate_path(Path(document_path), config)
    state = await session_mgr.get_or_open(svg_path)
    async with state.lock:
        session_mgr.check_revision(state, expected_revision)
        data = read_svg_file(state.svg_path, config)
        tree = etree.fromstring(data)
        defs = tree.find(f"{{{ns}}}defs")
        if defs is None:
            defs = etree.Element(f"{{{ns}}}defs")
            tree.insert(0, defs)

        p = etree.SubElement(defs, f"{{{ns}}}pattern")
        p.set("id", pat_id)
        p.set("width", str(width))
        p.set("height", str(height))
        p.set("patternUnits", "userSpaceOnUse")

        try:
            frag = etree.fromstring(f'<g xmlns="{ns}">{content_svg}</g>')
        except Exception as exc:
            raise InkscapeError(f"Invalid pattern content_svg: {exc}")

        for child in list(frag):
            p.append(child)

        new_svg = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", pretty_print=True)
        atomic_write_svg(state.svg_path, new_svg, config)
        new_rev = session_mgr.increment_revision(state)

    return _success(
        [{"type": "text", "text": f"pattern {pat_id}"}],
        {"pattern_id": pat_id, "revision": new_rev},
    )
