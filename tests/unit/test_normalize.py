"""Unit tests for response normalizer."""
from __future__ import annotations

from inkscape_mcp.normalize import (
    normalize_document_info,
    normalize_geometry_objects,
    normalize_query_all,
    normalize_query_axis,
)


class TestNormalizeQueryAll:
    def test_standard_output(self):
        """--query-all format: id,x,y,width,height per line"""
        raw = "svg1,10,10,80,60\nrect1,10,10,30,40\ncircle1,50,30,40,40"
        result = normalize_query_all(raw)
        assert len(result) == 3
        assert result[0] == {"id": "svg1", "x": 10.0, "y": 10.0, "width": 80.0, "height": 60.0}
        assert result[1] == {"id": "rect1", "x": 10.0, "y": 10.0, "width": 30.0, "height": 40.0}

    def test_single_object(self):
        raw = "r1,10,20,100,50"
        result = normalize_query_all(raw)
        assert len(result) == 1
        assert result[0]["id"] == "r1"
        assert result[0]["x"] == 10.0

    def test_empty_output(self):
        assert normalize_query_all("") == []
        assert normalize_query_all("\n\n") == []

    def test_negative_coords(self):
        raw = "r1,-10,-20,100,50"
        result = normalize_query_all(raw)
        assert result[0]["x"] == -10.0
        assert result[0]["y"] == -20.0


class TestNormalizeQueryAxis:
    def test_single_value(self):
        assert normalize_query_axis("40\n") == 40.0

    def test_empty(self):
        assert normalize_query_axis("") is None
        assert normalize_query_axis("\n") is None


class TestNormalizeGeometryObjects:
    def test_without_conversion(self):
        raw = "r1,10,20,100,50"
        result = normalize_geometry_objects(raw)
        assert result["r1"]["x"] == 10.0
        assert result["r1"]["y"] == 20.0
        assert result["r1"]["width"] == 100.0
        assert result["r1"]["height"] == 50.0

    def test_with_px_conversion(self):
        """F5: query returns px → converter turns to user-unit."""
        raw = "r1,200,100,300,150"
        # Factor = 2: px / 2 = user-unit
        def converter(v):
            return v / 2.0
        result = normalize_geometry_objects(raw, converter)
        assert result["r1"]["x"] == 100.0
        assert result["r1"]["y"] == 50.0
        assert result["r1"]["width"] == 150.0
        assert result["r1"]["height"] == 75.0


class TestNormalizeDocumentInfo:
    def test_basic(self):
        info = normalize_document_info(
            200.0, 200.0, (0, 0, 200, 200), 1.0, 5
        )
        assert info["width_px"] == 200.0
        assert info["viewBox"] == {"x": 0, "y": 0, "width": 200, "height": 200}
        assert info["px_to_user_unit"] == 1.0
        assert info["revision"] == 5

    def test_mm_document_factor(self):
        """A4 document: 210mm ≈ 793.7px at 96dpi, factor = 793.7/210."""
        info = normalize_document_info(
            793.7008, 1122.5197,
            (0, 0, 210, 297),
            3.77953, 3
        )
        assert info["px_to_user_unit"] > 1.0
        assert info["user_unit_to_px"] < 1.0
