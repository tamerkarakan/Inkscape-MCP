"""Unit tests for action chain builder."""
from __future__ import annotations

import pytest

from inkscape_mcp.actions import (
    build_actions_string,
    build_shell_command,
    chain_path_union,
    chain_set_attribute,
    chain_transform_translate,
    select_by_id,
    validate_run_actions,
)
from inkscape_mcp.exceptions import InkscapeSecurityError
from inkscape_mcp.security import SecurityConfig


class TestBuildShellCommand:
    def test_simple_action(self):
        assert build_shell_command("query-all") == "query-all"

    def test_action_with_arg(self):
        assert build_shell_command("select-by-id", "r1") == "select-by-id:r1"

    def test_action_with_special_chars_allowed(self):
        assert build_shell_command("object-set-attribute", "fill,red") == "object-set-attribute:fill,red"

    def test_invalid_action_name(self):
        with pytest.raises(InkscapeSecurityError):
            build_shell_command("; rm -rf /")

    def test_invalid_arg(self):
        with pytest.raises(InkscapeSecurityError):
            build_shell_command("select-by-id", "r1; rm")


class TestBuildActionsString:
    def test_single_action(self):
        result = build_actions_string([("query-all", None)])
        assert result == "query-all"

    def test_chain_multiple(self):
        result = build_actions_string([
            ("select-by-id", "r1"),
            ("object-set-attribute", "fill,red"),
            ("export-do", None),
        ])
        assert result == "select-by-id:r1;object-set-attribute:fill,red;export-do"

    def test_empty(self):
        assert build_actions_string([]) == ""


class TestSelectById:
    def test_prepends_select_by_id(self):
        actions = [("query-all", None)]
        result = select_by_id(actions, "r1", "c1")
        assert result == [
            ("select-by-id", "r1"),
            ("select-by-id", "c1"),
            ("query-all", None),
        ]

    def test_no_ids(self):
        actions = [("query-all", None)]
        result = select_by_id(actions)
        assert result == [("query-all", None)]


class TestChainPathUnion:
    def test_union_chain_structure(self):
        """Union must: object-to-path each operand, then path-union."""
        chain = chain_path_union("r1", "c1")
        # Verify contains the right actions (order matters less for our test)
        names = [name for name, _ in chain]
        assert "object-to-path" in names
        assert "path-union" in names
        assert "select-by-id" in names
        assert "select-clear" in names
        # Last action should be path-union
        assert names[-1] == "path-union"


class TestChainSetAttribute:
    def test_set_attribute(self):
        chain = chain_set_attribute("r1", "fill", "purple")
        assert ("object-set-attribute", "fill,purple") in chain
        assert ("select-by-id", "r1") in chain


class TestChainTransformTranslate:
    def test_translate(self):
        chain = chain_transform_translate("r1", 100, 0)
        assert ("transform-translate", "100,0") in chain
        assert ("select-by-id", "r1") in chain


class TestValidateRunActions:
    def test_valid_action(self, tmp_path):
        config = SecurityConfig(workspace_root=tmp_path)
        result = validate_run_actions(
            [{"name": "select-by-id", "arg": "r1"}], config
        )
        assert result == [("select-by-id", "r1")]

    def test_gui_action_rejected(self, tmp_path):
        config = SecurityConfig(workspace_root=tmp_path)
        with pytest.raises(InkscapeSecurityError, match="GUI"):
            validate_run_actions(
                [{"name": "window-open", "arg": None}], config
            )

    def test_unknown_action_rejected(self, tmp_path):
        config = SecurityConfig(workspace_root=tmp_path)
        with pytest.raises(InkscapeSecurityError, match="headless-safe"):
            validate_run_actions(
                [{"name": "tool-rect", "arg": None}], config
            )

    def test_invalid_action_name(self, tmp_path):
        config = SecurityConfig(workspace_root=tmp_path)
        with pytest.raises(InkscapeSecurityError):
            validate_run_actions(
                [{"name": "; rm -rf /", "arg": None}], config
            )
