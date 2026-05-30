from pathlib import Path

import pytest

from inkscape_mcp.server import create_server


def _sc(res):
    return res[1]


def _has_image(res):
    raw = res[0]
    content = raw if isinstance(raw, list) else [raw]
    return any(getattr(c, "type", None) == "image" for c in content)


async def _doc(server, name):
    return _sc(await server.call_tool(
        "document_create", {"doc_name": name, "width": 200, "height": 200}))["document_path"]


class TestPaint:
    """create_gradient (linear/radial) + create_pattern, defs + render."""

    async def test_linear_gradient_renders(self):
        """Linear gradient is written to <defs> and renders when referenced."""
        server = create_server()
        dp = await _doc(server, "paint_linear")
        g = _sc(await server.call_tool("create_gradient", {
            "document_path": dp, "gradient_type": "linear",
            "stops": [{"offset": 0, "color": "#ff0000"}, {"offset": 1, "color": "#0000ff", "opacity": 0.8}],
            "params": {"x1": 0, "y1": 0, "x2": 200, "y2": 0}}))
        svg = Path(dp).read_text(encoding="utf-8")
        assert "<linearGradient" in svg and svg.count("<stop") == 2
        _sc(await server.call_tool("element_create", {
            "document_path": dp, "element_type": "rect",
            "properties": {"x": 0, "y": 0, "width": 200, "height": 200, "fill": f"url(#{g['gradient_id']})"}}))
        assert _has_image(await server.call_tool("render_preview", {"document_path": dp}))

    async def test_radial_gradient(self):
        """Radial gradient is written to <defs>."""
        server = create_server()
        dp = await _doc(server, "paint_radial")
        _sc(await server.call_tool("create_gradient", {
            "document_path": dp, "gradient_type": "radial",
            "stops": [{"offset": 0, "color": "#fff"}, {"offset": 1, "color": "#000"}],
            "params": {"cx": 100, "cy": 100, "r": 80}}))
        assert "<radialGradient" in Path(dp).read_text(encoding="utf-8")

    async def test_pattern_renders(self):
        """Pattern is written to <defs> with its tile content and renders."""
        server = create_server()
        dp = await _doc(server, "paint_pattern")
        p = _sc(await server.call_tool("create_pattern", {
            "document_path": dp, "width": 20, "height": 20,
            "content_svg": '<circle cx="10" cy="10" r="6" fill="darkgreen"/>'}))
        svg = Path(dp).read_text(encoding="utf-8")
        assert "<pattern" in svg and "<circle" in svg
        _sc(await server.call_tool("element_create", {
            "document_path": dp, "element_type": "rect",
            "properties": {"x": 0, "y": 0, "width": 200, "height": 200, "fill": f"url(#{p['pattern_id']})"}}))
        assert _has_image(await server.call_tool("render_preview", {"document_path": dp}))

    async def test_pattern_rejects_malformed_content(self):
        """Malformed pattern content_svg is rejected."""
        server = create_server()
        dp = await _doc(server, "paint_badpat")
        with pytest.raises(Exception):
            await server.call_tool("create_pattern", {
                "document_path": dp, "width": 10, "height": 10, "content_svg": "<circle<bad"})
