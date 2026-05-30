from pathlib import Path

from lxml import etree

from inkscape_mcp.server import create_server


def _sc(res):
    return res[1]


def _order(dp):
    root = etree.parse(dp).getroot()
    return [e.get("id") for e in root if e.get("id")]


async def _doc(server, name):
    return _sc(await server.call_tool(
        "document_create", {"doc_name": name, "width": 200, "height": 200}))["document_path"]


class TestGeometryTier1:
    """ellipse, before_id z-insert, transform_element, reorder_element."""

    async def test_ellipse(self):
        """element_create supports ellipse (cx, cy, rx, ry)."""
        server = create_server()
        dp = await _doc(server, "geo_ellipse")
        _sc(await server.call_tool("element_create", {
            "document_path": dp, "element_type": "ellipse",
            "properties": {"cx": 100, "cy": 100, "rx": 60, "ry": 30, "fill": "teal"}}))
        svg = Path(dp).read_text(encoding="utf-8")
        assert "<ellipse" in svg and 'rx="60"' in svg and 'ry="30"' in svg

    async def test_before_id_inserts_under(self):
        """before_id inserts the new element below an existing one (z-order)."""
        server = create_server()
        dp = await _doc(server, "geo_before")
        top = _sc(await server.call_tool("element_create", {
            "document_path": dp, "element_type": "circle",
            "properties": {"cx": 50, "cy": 50, "r": 20, "fill": "blue"}}))["element_id"]
        under = _sc(await server.call_tool("element_create", {
            "document_path": dp, "element_type": "rect",
            "properties": {"x": 0, "y": 0, "width": 40, "height": 40, "fill": "red"},
            "before_id": top}))["element_id"]
        order = _order(dp)
        assert order.index(under) < order.index(top)

    async def test_transform_composes(self):
        """transform_element composes scale then rotate onto the transform attr."""
        server = create_server()
        dp = await _doc(server, "geo_transform")
        eid = _sc(await server.call_tool("element_create", {
            "document_path": dp, "element_type": "circle",
            "properties": {"cx": 60, "cy": 60, "r": 30, "fill": "green"}}))["element_id"]
        _sc(await server.call_tool("transform_element", {
            "document_path": dp, "object_id": eid, "operation": "scale", "params": {"sx": 1, "sy": 0.5}}))
        tr = _sc(await server.call_tool("transform_element", {
            "document_path": dp, "object_id": eid, "operation": "rotate", "params": {"angle": 30}}))
        assert "scale(" in tr["transform"] and "rotate(30" in tr["transform"]

    async def test_reorder_top(self):
        """reorder_element top moves an element above its siblings."""
        server = create_server()
        dp = await _doc(server, "geo_reorder")
        a = _sc(await server.call_tool("element_create", {
            "document_path": dp, "element_type": "rect",
            "properties": {"x": 0, "y": 0, "width": 40, "height": 40, "fill": "red"}}))["element_id"]
        b = _sc(await server.call_tool("element_create", {
            "document_path": dp, "element_type": "circle",
            "properties": {"cx": 50, "cy": 50, "r": 20, "fill": "blue"}}))["element_id"]
        # a is below b; move a to top
        _sc(await server.call_tool("reorder_element", {
            "document_path": dp, "object_id": a, "position": "top"}))
        order = _order(dp)
        assert order.index(a) > order.index(b)
