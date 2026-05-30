from pathlib import Path

from inkscape_mcp.server import create_server

GOOD = {
    "scans": 2,
    "smooth": False,
    "stack": True,
    "remove_background": False,
    "speckles": 0,
    "smooth_corners": 0.0,
    "optimize": False,
}


def _sc(res):
    return res[1]


async def _doc_with_image(server, name):
    doc = _sc(await server.call_tool("document_create", {"doc_name": name, "width": 200, "height": 200}))
    dp = doc["document_path"]
    _sc(await server.call_tool("element_create", {"document_path": dp, "element_type": "rect", "properties": {"x": 20, "y": 20, "width": 160, "height": 160, "fill": "black"}}))
    png = _sc(await server.call_tool("export_document", {"document_path": dp, "output_name": name + "_ras", "export_format": "png"}))["output_path"]
    doc2 = _sc(await server.call_tool("document_create", {"doc_name": name + "_v", "width": 200, "height": 200}))
    dp2 = doc2["document_path"]
    img = _sc(await server.call_tool("import_image", {"document_path": dp2, "image_path": png, "width": 200, "height": 200}))
    return dp2, img


class TestImageTools:
    """import_image + trace_bitmap end-to-end through the real server entry point."""

    async def test_import_image_embeds(self):
        """import_image embeds an <image> with the returned id."""
        server = create_server()
        dp2, img = await _doc_with_image(server, "test_import")
        assert img["element_type"] == "image"
        svg_text = Path(dp2).read_text(encoding="utf-8", errors="replace")
        assert "<image" in svg_text
        assert img["element_id"] in svg_text

    async def test_import_image_from_base64_data(self):
        """import_image accepts raw base64 image_data (no file on disk)."""
        import base64
        server = create_server()
        # build a real PNG via the tools, read its bytes, re-embed via image_data
        dpa = _sc(await server.call_tool(
            "document_create", {"doc_name": "imgdata_src", "width": 80, "height": 80}))["document_path"]
        await server.call_tool("element_create", {
            "document_path": dpa, "element_type": "rect",
            "properties": {"x": 10, "y": 10, "width": 60, "height": 60, "fill": "black"}})
        png = _sc(await server.call_tool("export_document", {
            "document_path": dpa, "output_name": "imgdata_src", "export_format": "png"}))["output_path"]
        b64 = base64.b64encode(Path(png).read_bytes()).decode("ascii")

        dpb = _sc(await server.call_tool(
            "document_create", {"doc_name": "imgdata_dst", "width": 200, "height": 200}))["document_path"]
        img = _sc(await server.call_tool("import_image", {
            "document_path": dpb, "image_data": b64, "image_format": "png",
            "width": 200, "height": 200}))
        assert img["element_type"] == "image"
        svg = Path(dpb).read_text(encoding="utf-8", errors="replace")
        assert "<image" in svg and "data:image/png;base64," in svg

    async def test_trace_creates_path_and_excludes_structural_ids(self):
        """trace_bitmap produces <path> and id_map.created omits structural ids."""
        server = create_server()
        dp2, img = await _doc_with_image(server, "test_trace_path")
        trace_res = _sc(await server.call_tool("trace_bitmap", {"document_path": dp2, "image_id": img["element_id"], **GOOD}))
        id_map = trace_res["id_map"]
        assert id_map["created"]
        svg_text = Path(dp2).read_text(encoding="utf-8", errors="replace")
        assert "<path" in svg_text
        for cid in id_map["created"]:
            assert not cid.startswith("svg")
            assert not cid.startswith("namedview")
            assert not cid.startswith("metadata")
        assert "<image" in svg_text

    async def test_trace_remove_source_deletes_image(self):
        """trace_bitmap with remove_source deletes the source <image>."""
        server = create_server()
        dp2, img = await _doc_with_image(server, "test_trace_remove")
        trace_res = _sc(await server.call_tool("trace_bitmap", {"document_path": dp2, "image_id": img["element_id"], "remove_source": True, **GOOD}))
        id_map = trace_res["id_map"]
        assert id_map["created"]
        assert img["element_id"] in id_map["destroyed"]
        svg_text = Path(dp2).read_text(encoding="utf-8", errors="replace")
        assert img["element_id"] not in svg_text
        assert "<path" in svg_text
