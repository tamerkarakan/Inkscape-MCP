"""Shared fixtures for all tests."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from inkscape_mcp.security import SecurityConfig
from inkscape_mcp.session import SessionManager

# Path to project root (for reference/ and fixtures)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp_workspace() -> Path:
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory(prefix="inkscape_mcp_test_") as tmp:
        yield Path(tmp)


@pytest.fixture
def security_config(tmp_workspace: Path) -> SecurityConfig:
    """Create a security config with a temp workspace."""
    return SecurityConfig(workspace_root=tmp_workspace)


@pytest.fixture
def session_manager(security_config: SecurityConfig) -> SessionManager:
    """Create a session manager."""
    return SessionManager(security_config)


@pytest.fixture
def base_input_svg(tmp_workspace: Path) -> Path:
    """Copy base-input.svg fixture into workspace."""
    src = PROJECT_ROOT / "reference" / "fixtures" / "base-input.svg"
    dst = tmp_workspace / "base.svg"
    dst.write_bytes(src.read_bytes())
    return dst


@pytest.fixture
def inkscape_bin() -> str | None:
    """Inkscape binary path from env, or None if not available."""
    return os.environ.get("INKSCAPE_BIN")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end tests requiring real Inkscape binary"
    )
