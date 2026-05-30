from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .exceptions import InkscapeError, InkscapeTimeoutError, InkscapeProcessError, parse_stderr


class GuiSession:
    """Inkscape GUI penceresini yöneten oturum (live --active-window driver)."""

    def __init__(self, app_id: str, svg_path: Path, config):
        self.app_id = app_id
        self.svg_path = svg_path
        self.config = config
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._inkscape_bin: str = ""
        self._inkscape_gui_bin: str = ""

    def _resolve_binaries(self) -> tuple[str, str]:
        """Inkscape binary yollarını çözümle. (komut=.com, gui=.exe) ikilisi."""
        bin_env = os.environ.get("INKSCAPE_BIN", "")
        gui_env = os.environ.get("INKSCAPE_GUI_BIN", "")

        if bin_env:
            cmd_bin = bin_env
        else:
            cmd_bin = "inkscape.com" if os.name == "nt" else "inkscape"

        if gui_env:
            gui_bin = gui_env
        elif os.name == "nt":
            if cmd_bin.lower().endswith(".com"):
                gui_bin = cmd_bin[:-4] + ".exe"
            else:
                gui_bin = cmd_bin
        else:
            gui_bin = "inkscape"

        return cmd_bin, gui_bin

    async def start(self):
        """Inkscape GUI'yi detached başlat, pencere açılana kadar bekle."""
        cmd_bin, gui_bin = self._resolve_binaries()
        self._inkscape_bin = cmd_bin
        self._inkscape_gui_bin = gui_bin

        arg_list = [gui_bin, f"--app-id-tag={self.app_id}", str(self.svg_path)]
        self._proc = await asyncio.create_subprocess_exec(
            *arg_list,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        # Pencere --active-window komutlarını kabul edene kadar bekle.
        # (Fizibilite spike'ında ~7s gerekti; tutuculuk için bekleme yapılandırılabilir.)
        await asyncio.sleep(float(os.environ.get("INKSCAPE_GUI_STARTUP_S", "6")))

    async def _run_inkscape_command(self, args: list[str], timeout: Optional[int] = None) -> str:
        """Genel inkscape.com çağrısı, timeout + child-kill ile."""
        if timeout is None:
            timeout = getattr(self.config, "default_timeout", 30)

        proc = await asyncio.create_subprocess_exec(
            self._inkscape_bin, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await self._kill_pid(proc.pid)
            raise InkscapeTimeoutError(f"inkscape.com timeout after {timeout}s")

        # F18: exit code GÜVENİLMEZ — hata yalnız stderr'de. Dönen hatayı RAISE et.
        if stderr:
            err = parse_stderr(stderr.decode("utf-8", errors="replace"))
            if err:
                raise err
        return stdout.decode("utf-8", errors="replace")

    @staticmethod
    async def _kill_pid(pid: int):
        if os.name == "nt":
            await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        else:
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass

    async def run_actions(self, actions: str) -> str:
        """Aktif (canlı) pencereye komut zinciri gönder, stdout döndür.

        NOT: `actions` server tarafından kurulmuş, doğrulanmış bir zincir kabul edilir
        (içinde ';' ve ':' ayraçları olduğu için string bütünü sanitize edilmez).
        """
        args = [
            f"--app-id-tag={self.app_id}",
            "--active-window",
            f"--actions={actions}",
        ]
        return await self._run_inkscape_command(args)

    async def export_live(self, out_path: Path, fmt: str = "svg") -> Path:
        """Canlı pencerenin GÜNCEL durumunu export et."""
        actions = f"export-filename:{out_path};export-type:{fmt};export-do"
        await self.run_actions(actions)
        if not out_path.exists():
            raise InkscapeError(f"Live export failed: {out_path} not found")
        return out_path

    async def close(self):
        """Bu oturumun GUI sürecini (ve ağacını) sonlandır."""
        if self._proc and self._proc.returncode is None:
            await self._kill_pid(self._proc.pid)
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
        self._proc = None


class GuiSessionManager:
    """app_id -> GuiSession; her oturum için lock."""

    def __init__(self, config):
        self.config = config
        self._sessions: dict[str, GuiSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, app_id: str) -> asyncio.Lock:
        if app_id not in self._locks:
            self._locks[app_id] = asyncio.Lock()
        return self._locks[app_id]

    async def get_or_start(self, app_id: str, svg_path: Path) -> GuiSession:
        async with self._get_lock(app_id):
            existing = self._sessions.get(app_id)
            if existing is None or existing._proc is None:
                session = GuiSession(app_id, svg_path, self.config)
                await session.start()
                self._sessions[app_id] = session
            return self._sessions[app_id]

    async def close(self, app_id: str) -> bool:
        """Tek bir oturumu kapat. Oturum vardıysa True döner."""
        async with self._get_lock(app_id):
            session = self._sessions.pop(app_id, None)
            if session is None:
                return False
            if session._proc is not None:
                await session.close()
            return True

    async def close_all(self):
        for session in list(self._sessions.values()):
            if session._proc is not None:
                await session.close()
        self._sessions.clear()
        self._locks.clear()
