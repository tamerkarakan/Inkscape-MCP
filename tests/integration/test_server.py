"""
Integration tests: server creation, injection protection, concurrency.

These tests verify the server starts correctly and core safety
mechanisms work (Madde 2/3/8/14 compliance).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from lxml import etree

from inkscape_mcp.exceptions import (
    InkscapeSecurityError,
    StaleRevisionError,
)
from inkscape_mcp.security import SecurityConfig, validate_action_arg
from inkscape_mcp.session import SessionManager, atomic_write_svg


# ═══════════════════════════════════════════════════════
#  T-1: Server creation smoke test
# ═══════════════════════════════════════════════════════


class TestServerCreation:
    """Verify server can be imported, created, and tools/resources are registered."""

    def test_create_server_imports_and_builds(self):
        """Server module can be imported and create_server() returns a FastMCP instance."""
        from inkscape_mcp.server import create_server
        server = create_server()
        assert server is not None
        # All 11 tools registered (7 headless + 4 GUI live-driver)
        tools = list(server._tool_manager._tools.keys())
        assert "document_create" in tools
        assert "element_create" in tools
        assert "element_update" in tools
        assert "query_geometry" in tools
        assert "export_document" in tools
        assert "render_preview" in tools
        assert "run_actions" in tools
        assert "gui_open" in tools
        assert "gui_apply" in tools
        assert "gui_export" in tools
        assert "gui_close" in tools
        assert "import_image" in tools
        assert "trace_bitmap" in tools
        assert "ask_user" in tools
        assert len(tools) == 14

    def test_resources_registered(self):
        """All required resources are registered (capabilities, doc-info, svg, preview)."""
        from inkscape_mcp.server import create_server
        server = create_server()
        # Static resources
        static = list(server._resource_manager._resources.keys())
        assert "inkscape://session/capabilities" in static
        # Templated resources
        templates = list(server._resource_manager._templates.keys())
        assert any("document-info" in t for t in templates)
        assert any("svg" in t for t in templates)
        assert any("preview" in t for t in templates)
        # Total: 2 static + 3 templated
        assert len(static) == 2
        assert len(templates) == 3

    def test_tool_annotations_present(self):
        """Each tool has required annotations (readOnly/destructive hints)."""
        from inkscape_mcp.server import create_server
        server = create_server()
        for tool_name, tool in server._tool_manager._tools.items():
            assert tool.annotations is not None, f"{tool_name} missing annotations"
            # Verify hints are boolean
            assert isinstance(tool.annotations.readOnlyHint, bool)
            assert isinstance(tool.annotations.destructiveHint, bool)
            assert isinstance(tool.annotations.idempotentHint, bool)
            assert isinstance(tool.annotations.openWorldHint, bool)

    def test_output_schema_present_for_all_tools(self):
        """Madde 9a: every tool's output_schema must be non-None (TypedDict return type)."""
        from inkscape_mcp.server import create_server
        server = create_server()
        tools = server._tool_manager.list_tools()
        assert len(tools) == 14, f"Expected 14 tools, got {len(tools)}"
        # render_preview returns an inline FastMCP Image (not structured data),
        # so it intentionally has no output_schema.
        no_schema_ok = {"render_preview"}
        for t in tools:
            if t.name in no_schema_ok:
                continue
            assert t.output_schema is not None, (
                f"Tool '{t.name}' has output_schema=None — "
                f"return type annotation missing or not TypedDict"
            )


# ═══════════════════════════════════════════════════════
#  T-2: Production run_actions injection test
# ═══════════════════════════════════════════════════════


class TestRunActionsInjectionProtection:
    """Verify that user-supplied values containing ; or : are rejected."""

    def test_object_id_with_semicolon_rejected(self, tmp_workspace):
        """object_id="r1;export-do" must be rejected (action injection)."""
        config = SecurityConfig(workspace_root=tmp_workspace)
        with pytest.raises(InkscapeSecurityError):
            validate_action_arg("r1;export-do")

    def test_object_id_with_colon_rejected(self, tmp_workspace):
        """object_id with : must be rejected."""
        config = SecurityConfig(workspace_root=tmp_workspace)
        with pytest.raises(InkscapeSecurityError):
            validate_action_arg("r1:export-do")

    def test_valid_object_id_accepted(self, tmp_workspace):
        """Clean object IDs pass validation."""
        config = SecurityConfig(workspace_root=tmp_workspace)
        # Should not raise
        validate_action_arg("r1")
        validate_action_arg("c1")
        validate_action_arg("rect_123")

    def test_action_param_value_with_semicolon_rejected(self, tmp_workspace):
        """Action param values with ; must be rejected."""
        config = SecurityConfig(workspace_root=tmp_workspace)
        with pytest.raises(InkscapeSecurityError):
            validate_action_arg("fill,red;export-do")


# ═══════════════════════════════════════════════════════
#  T-3: Concurrency test — lock serialization + stale revision
# ═══════════════════════════════════════════════════════


_SVG_BASE = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
  <rect id="r1" x="10" y="10" width="50" height="40"/>
  <circle id="c1" cx="100" cy="100" r="20"/>
</svg>"""


class TestConcurrency:
    """Verify that concurrent mutations serialize and revision stays consistent."""

    async def _concurrent_updates(self, svg_path: Path, config: SecurityConfig):
        """Run two concurrent element_update calls and return final revision."""
        session_mgr = SessionManager(config)
        state = await session_mgr.get_or_open(svg_path)

        async def update_fill(object_id: str, fill: str, expected_rev: int | None):
            from inkscape_mcp.tools import tool_element_update
            return await tool_element_update(
                session_mgr, config,
                document_path=str(svg_path),
                object_id=object_id,
                properties={"fill": fill},
                expected_revision=expected_rev,
            )

        # Launch both concurrently
        results = await asyncio.gather(
            update_fill("r1", "red", None),
            update_fill("c1", "blue", None),
        )

        return state.revision, results

    def test_concurrent_updates_serialize_and_revision_consistent(
        self, tmp_workspace
    ):
        """Two concurrent updates: both succeed, revision advances by 2."""
        config = SecurityConfig(workspace_root=tmp_workspace)
        svg_path = tmp_workspace / "test.svg"
        atomic_write_svg(svg_path, _SVG_BASE, config)

        revision, results = asyncio.run(
            self._concurrent_updates(svg_path, config)
        )

        # Revision should have advanced by 2 (one per update)
        assert revision == 3  # started at 1, +1 +1 = 3

        # Both updates should succeed (not isError)
        for r in results:
            assert r.get("isError") is not True

    def test_stale_revision_race_detected(self, tmp_workspace):
        """When expected_revision is stale, mutation is rejected."""
        config = SecurityConfig(workspace_root=tmp_workspace)
        svg_path = tmp_workspace / "stale_test.svg"
        atomic_write_svg(svg_path, _SVG_BASE, config)

        async def race():
            from inkscape_mcp.tools import tool_element_update
            session_mgr = SessionManager(config)

            # First update: rev 1→2
            r1 = await tool_element_update(
                session_mgr, config,
                document_path=str(svg_path),
                object_id="r1",
                properties={"fill": "green"},
                expected_revision=1,
            )
            assert r1.get("isError") is not True

            # Second update with stale expected_revision=1 → should fail
            with pytest.raises(StaleRevisionError):
                await tool_element_update(
                    session_mgr, config,
                    document_path=str(svg_path),
                    object_id="c1",
                    properties={"fill": "yellow"},
                    expected_revision=1,
                )

        asyncio.run(race())
