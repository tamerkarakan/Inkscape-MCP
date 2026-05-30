from pathlib import Path

import pytest

from inkscape_mcp.server import create_server


def _sc(res):
    return res[1]


async def _new_doc(server, name):
    doc = _sc(await server.call_tool(
        "document_create", {"doc_name": name, "width": 200, "height": 200}))
    return doc["document_path"]


class TestAuthoring:
    """element_create attribute pass-through, export extension, write_svg."""

    async def test_element_create_keeps_hyphenated_and_extra_attrs(self):
        """Bug A: hyphenated / non-allowlisted attributes must not be dropped."""
        server = create_server()
        dp = await _new_doc(server, "auth_passthrough")
        _sc(await server.call_tool("element_create", {
            "document_path": dp, "element_type": "text",
            "properties": {"x": 100, "y": 100, "text": "Hi",
                           "font-size": 72, "font-weight": "bold",
                           "letter-spacing": 9, "text-anchor": "middle"},
        }))
        _sc(await server.call_tool("element_create", {
            "document_path": dp, "element_type": "circle",
            "properties": {"cx": 50, "cy": 50, "r": 20, "fill": "none",
                           "stroke": "#DD8A3E", "stroke-width": 5,
                           "stroke-linecap": "round"},
        }))
        svg = Path(dp).read_text(encoding="utf-8", errors="replace")
        for needed in ('font-size="72"', 'font-weight="bold"', 'letter-spacing="9"',
                       'text-anchor="middle"', 'stroke-width="5"', 'stroke-linecap="round"'):
            assert needed in svg, f"dropped attribute: {needed}"

    async def test_export_strips_double_extension(self):
        """Bug B: output_name already ending in .png must not become .png.png."""
        server = create_server()
        dp = await _new_doc(server, "auth_export")
        await server.call_tool("element_create", {
            "document_path": dp, "element_type": "rect",
            "properties": {"x": 10, "y": 10, "width": 80, "height": 80, "fill": "black"},
        })
        exp = _sc(await server.call_tool("export_document", {
            "document_path": dp, "output_name": "auth_export_out.png",
            "export_format": "png",
        }))
        op = exp["output_path"]
        assert op.endswith("auth_export_out.png")
        assert not op.endswith(".png.png")
        assert Path(op).exists()

    async def test_write_svg_saves_valid(self):
        """write_svg saves a well-formed SVG to the workspace."""
        server = create_server()
        svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<svg xmlns="http://www.w3.org/2000/svg" width="60" height="60" '
               'viewBox="0 0 60 60"><circle cx="30" cy="30" r="20" fill="teal"/></svg>')
        r = _sc(await server.call_tool("write_svg", {"doc_name": "auth_write", "svg_content": svg}))
        dp = r["document_path"]
        assert r["revision"] == 1
        assert Path(dp).exists()
        assert "<circle" in Path(dp).read_text(encoding="utf-8")

    async def test_write_svg_rejects_malformed(self):
        """write_svg rejects malformed XML."""
        server = create_server()
        with pytest.raises(Exception):
            await server.call_tool("write_svg", {"doc_name": "auth_bad", "svg_content": "<svg><oops</svg>"})
