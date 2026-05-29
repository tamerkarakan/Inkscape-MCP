"""Unit tests for security module."""
from __future__ import annotations

import pytest
from pathlib import Path

from inkscape_mcp.exceptions import InkscapeSecurityError
from inkscape_mcp.security import (
    SecurityConfig,
    is_gui_action,
    is_headless_safe,
    validate_path,
    validate_path_traversal,
    validate_svg_size,
    validate_action_name,
    validate_action_arg,
)


class TestValidatePath:
    def test_path_in_workspace(self, tmp_workspace):
        config = SecurityConfig(workspace_root=tmp_workspace)
        inside = tmp_workspace / "doc.svg"
        inside.write_text("<svg/>")
        result = validate_path(inside, config)
        assert result is not None

    def test_path_outside_workspace(self, tmp_workspace):
        config = SecurityConfig(workspace_root=tmp_workspace)
        outside = Path("/tmp/evil.svg")  # Unix
        with pytest.raises(InkscapeSecurityError, match="outside"):
            validate_path(outside, config)

    def test_path_traversal(self, tmp_workspace):
        config = SecurityConfig(workspace_root=tmp_workspace)
        traversal = tmp_workspace / ".." / "evil.svg"
        with pytest.raises(InkscapeSecurityError):
            validate_path(traversal, config)


class TestValidatePathTraversal:
    def test_rejects_dotdot(self):
        with pytest.raises(InkscapeSecurityError, match="traversal"):
            validate_path_traversal("doc/../../evil.svg")

    def test_accepts_normal_path(self):
        # Should not raise
        validate_path_traversal("doc/sub/file.svg")


class TestValidateSvgSize:
    def test_within_limit(self):
        config = SecurityConfig(workspace_root=Path("/tmp"), max_svg_size_bytes=1000)
        # Should not raise
        validate_svg_size(b"<svg/>", config)

    def test_exceeds_limit(self):
        config = SecurityConfig(workspace_root=Path("/tmp"), max_svg_size_bytes=10)
        with pytest.raises(InkscapeSecurityError, match="too large"):
            validate_svg_size(b"<svg>" + b"x" * 100 + b"</svg>", config)


class TestValidateActionName:
    def test_valid_names(self):
        validate_action_name("select-by-id")
        validate_action_name("path-union")
        validate_action_name("object-set-attribute")

    def test_invalid_name_semicolon(self):
        with pytest.raises(InkscapeSecurityError):
            validate_action_name("select; rm")

    def test_invalid_name_spaces(self):
        with pytest.raises(InkscapeSecurityError):
            validate_action_name("select by id")


class TestValidateActionArg:
    def test_valid_args(self):
        validate_action_arg("r1")
        validate_action_arg("fill,red")
        validate_action_arg("100,0")

    def test_invalid_arg_semicolon(self):
        with pytest.raises(InkscapeSecurityError):
            validate_action_arg("r1; export-do")


class TestGuiActionDetection:
    def test_gui_actions(self):
        assert is_gui_action("window-open") is True
        assert is_gui_action("window-crash") is True
        assert is_gui_action("file-open-window") is True

    def test_non_gui_actions(self):
        assert is_gui_action("select-by-id") is False
        assert is_gui_action("path-union") is False


class TestHeadlessSafe:
    def test_core_actions(self):
        assert is_headless_safe("select-by-id") is True
        assert is_headless_safe("path-union") is True
        assert is_headless_safe("query-all") is True

    def test_gui_actions_not_safe(self):
        assert is_headless_safe("window-open") is False

    def test_unknown_action_not_safe(self):
        assert is_headless_safe("tool-rect") is False
