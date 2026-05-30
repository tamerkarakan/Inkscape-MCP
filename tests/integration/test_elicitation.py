from types import SimpleNamespace
from pathlib import Path

from inkscape_mcp.tools import _confirm_destructive, tool_ask_user
from inkscape_mcp.security import SecurityConfig


class _MockCtx:
    def __init__(self, action="accept", confirm=True, raises=False):
        self._action = action
        self._confirm = confirm
        self._raises = raises

    async def elicit(self, message, schema):
        if self._raises:
            raise RuntimeError("no elicitation capability")
        if self._action == "accept":
            return SimpleNamespace(
                action="accept",
                data=schema(confirm=self._confirm) if "confirm" in schema.model_fields else schema(response="hi"),
            )
        return SimpleNamespace(action=self._action)


class TestElicitationGate:
    """Tests for the destructive-operation confirmation gate + ask_user."""

    async def test_confirm_none_ctx_proceeds(self):
        """_confirm_destructive returns True when ctx is None."""
        cfg = SecurityConfig(workspace_root=Path("."))
        assert await _confirm_destructive(None, cfg, "x") is True

    async def test_confirm_accept_true(self):
        """Accept with confirm=True returns True."""
        cfg = SecurityConfig(workspace_root=Path("."))
        ctx = _MockCtx("accept", confirm=True)
        assert await _confirm_destructive(ctx, cfg, "x") is True

    async def test_confirm_accept_false_blocks(self):
        """Accept with confirm=False returns False."""
        cfg = SecurityConfig(workspace_root=Path("."))
        ctx = _MockCtx("accept", confirm=False)
        assert await _confirm_destructive(ctx, cfg, "x") is False

    async def test_confirm_decline_blocks(self):
        """Decline returns False."""
        cfg = SecurityConfig(workspace_root=Path("."))
        ctx = _MockCtx("decline")
        assert await _confirm_destructive(ctx, cfg, "x") is False

    async def test_confirm_unsupported_proceeds(self):
        """Client that cannot elicit returns True (degrade gracefully)."""
        cfg = SecurityConfig(workspace_root=Path("."))
        ctx = _MockCtx(raises=True)
        assert await _confirm_destructive(ctx, cfg, "x") is True

    async def test_confirm_disabled_proceeds(self):
        """When confirmation disabled, return True even if user would decline."""
        cfg = SecurityConfig(workspace_root=Path("."))
        cfg.require_confirmation_for_destructive = False
        ctx = _MockCtx("decline")
        assert await _confirm_destructive(ctx, cfg, "x") is True

    async def test_ask_user_accept(self):
        """tool_ask_user with accept returns answered=True."""
        ctx = _MockCtx("accept")
        r = await tool_ask_user(ctx, "Q", ["a", "b"])
        assert r["answered"] is True
        assert r["action"] == "accept"
        assert r["response"] == "hi"

    async def test_ask_user_none_ctx_unsupported(self):
        """tool_ask_user with None ctx returns unsupported."""
        r = await tool_ask_user(None, "Q")
        assert r["action"] == "unsupported"
        assert r["answered"] is False
