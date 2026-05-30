"""Integration test for graceful shutdown of GUI sessions."""


async def test_run_closes_gui_sessions_on_shutdown(monkeypatch):
    from inkscape_mcp import server as srv
    from mcp.server.fastmcp import FastMCP
    from inkscape_mcp.gui_session import GuiSessionManager

    calls = []

    async def _noop_stdio(self):
        return None

    async def _recording_close_all(self):
        calls.append(True)

    monkeypatch.setattr(FastMCP, "run_stdio_async", _noop_stdio, raising=False)
    monkeypatch.setattr(GuiSessionManager, "close_all", _recording_close_all, raising=False)

    await srv.run()

    assert calls == [True], "close_all was not awaited on shutdown"
