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
    """Build an MCP success result."""
    result: dict = {"content": content}
    if structured:
        result["structuredContent"] = structured
    return result


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

        else:
            raise InkscapeError(f"Unsupported element_type: {element_type}")

        # Serialize and atomically write
        new_svg = etree.tostring(
            tree,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )
        atomic_write_svg(state.svg_path, new_svg, config)

        # Update revision
        state.revision += 1
        new_rev = state.revision

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
        state.revision += 1
        new_rev = state.revision

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


async def tool_render_preview(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    width: int = 400,
    height: int | None = None,
) -> dict:
    """Render a PNG preview of the current SVG.

    Returns image content inline or resource_link (Madde 11).
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

            # Size check: if exceeds max_preview_bytes, return resource_link
            if len(png_data) > config.max_preview_bytes:
                return _success(
                    [{"type": "text", "text": "Preview too large; use resource link"}],
                    {
                        "preview_available": True,
                        "preview_size": len(png_data),
                        "preview_resource": f"inkscape://session/{state.svg_path.stem}/preview",
                    },
                )

            import base64
            b64 = base64.b64encode(png_data).decode()

            return _success(
                [
                    {
                        "type": "image",
                        "data": b64,
                        "mimeType": "image/png",
                    }
                ],
                {
                    "preview_available": True,
                    "preview_size": len(png_data),
                    "revision": state.revision,
                },
            )
        finally:
            try:
                tmp_png.unlink(missing_ok=True)
            except OSError:
                pass


# ── run_actions (Inkscape CLI escape hatch) ──


async def tool_run_actions(
    session_mgr: SessionManager,
    config: SecurityConfig,
    document_path: str,
    operation: str,
    object_ids: list[str],
    action_params: dict[str, Any] | None = None,
    expected_revision: int | None = None,
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

    # Check destructive policy
    destructive_ops = {"path_union", "path_difference", "path_intersection",
                       "path_exclusion"}
    if operation in destructive_ops and config.require_confirmation_for_destructive:
        # For v1: allow but annotate. Full policy gate in later phase.
        pass

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
            actions = chain_transform_translate(object_ids[0], dx, dy)
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
            _run_inkscape_sync(
                ["--actions=" + action_str, str(state.svg_path)],
                config,
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
        state.revision += 1
        new_rev = state.revision

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
