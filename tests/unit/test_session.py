"""Unit tests for session module."""
from __future__ import annotations

import asyncio

import pytest
from lxml import etree

from inkscape_mcp.exceptions import (
    DocumentNotFoundError,
    IdNotFoundError,
    StaleRevisionError,
)
from inkscape_mcp.security import SecurityConfig
from inkscape_mcp.session import atomic_write_svg


class TestAtomicWrite:
    def test_write_and_read(self, tmp_workspace, security_config):
        svg_path = tmp_workspace / "test.svg"
        size = atomic_write_svg(svg_path, b"<svg/>", security_config)
        assert size > 0
        assert svg_path.exists()
        assert svg_path.read_text() == "<svg/>"

    def test_atomic_replace(self, tmp_workspace, security_config):
        svg_path = tmp_workspace / "test.svg"
        atomic_write_svg(svg_path, b"<svg>old</svg>", security_config)
        atomic_write_svg(svg_path, b"<svg>new</svg>", security_config)
        assert svg_path.read_text() == "<svg>new</svg>"

    def test_size_limit(self, tmp_workspace, security_config):
        config = SecurityConfig(workspace_root=tmp_workspace, max_svg_size_bytes=10)
        svg_path = tmp_workspace / "test.svg"
        with pytest.raises(Exception):
            atomic_write_svg(svg_path, b"x" * 1000, config)


class TestSessionManager:
    def test_open_existing(self, session_manager, base_input_svg):
        state = asyncio.run(session_manager.get_or_open(base_input_svg))
        assert state.revision == 1
        assert state.view_box == (0, 0, 200, 200)
        assert state.width_px == 200.0

    def test_open_nonexistent_raises(self, session_manager, tmp_workspace):
        path = tmp_workspace / "nonexistent.svg"
        with pytest.raises(DocumentNotFoundError):
            asyncio.run(session_manager.get_or_open(path))

    def test_register_new(self, session_manager, tmp_workspace):
        svg_path = tmp_workspace / "new_doc.svg"
        svg_path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"/>')
        state = session_manager.register_new(svg_path, revision=1)
        assert state.revision == 1
        assert state.view_box == (0, 0, 100, 100)

    def test_px_to_user_conversion(self, session_manager, tmp_workspace):
        # factor = 1: px = user-unit
        svg_path = tmp_workspace / "factor1.svg"
        svg_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200"/>'
        )
        state = session_manager.register_new(svg_path)
        assert state.px_to_user_unit == 1.0
        assert session_manager.px_to_user(state, 50.0) == 50.0

    def test_px_to_user_different_factor(self, session_manager, tmp_workspace):
        # width=400, viewBox=0 0 200 200 → factor=2 (px/user = 2)
        svg_path = tmp_workspace / "factor2.svg"
        svg_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 200 200"/>'
        )
        state = session_manager.register_new(svg_path)
        assert state.px_to_user_unit == 2.0
        # 100 px → 50 user units
        assert session_manager.px_to_user(state, 100.0) == 50.0

    def test_revision_check_passes(self, session_manager, base_input_svg):
        state = asyncio.run(session_manager.get_or_open(base_input_svg))
        # Should not raise
        session_manager.check_revision(state, None)
        session_manager.check_revision(state, 1)

    def test_revision_check_stale(self, session_manager, base_input_svg):
        state = asyncio.run(session_manager.get_or_open(base_input_svg))
        with pytest.raises(StaleRevisionError):
            session_manager.check_revision(state, 2)

    def test_collect_ids(self, session_manager, base_input_svg):
        asyncio.run(session_manager.get_or_open(base_input_svg))
        tree = etree.parse(str(base_input_svg)).getroot()
        ids = session_manager.collect_ids(tree)
        assert "r1" in ids
        assert "c1" in ids
        assert "p1" in ids

    def test_diff_ids_union_style(self, session_manager):
        before = {"r1", "c1", "p1"}
        after = {"r1", "p1"}  # c1 destroyed by path-union
        result = session_manager.diff_ids(before, after)
        assert "c1" in result["destroyed"]
        assert result["survived"] == {"r1": "r1", "p1": "p1"}
        assert result["created"] == []

    def test_diff_ids_with_new(self, session_manager):
        before = {"r1"}
        after = {"r1", "r2"}  # r2 created
        result = session_manager.diff_ids(before, after)
        assert "r2" in result["created"]
        assert result["destroyed"] == []

    def test_id_not_found(self, session_manager, base_input_svg):
        asyncio.run(session_manager.get_or_open(base_input_svg))
        tree = etree.parse(str(base_input_svg)).getroot()
        with pytest.raises(IdNotFoundError):
            session_manager.check_id_exists(tree, "nonexistent_id")
