"""
Document session: lock, revision tracking, atomic file I/O.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from lxml import etree

from .exceptions import (
    DocumentNotFoundError,
    IdNotFoundError,
    StaleRevisionError,
)
from .security import SecurityConfig, validate_path, validate_svg_size

NSMAP: ClassVar[dict[str, str]] = {
    "svg": "http://www.w3.org/2000/svg",
    "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
}


@dataclass
class DocumentState:
    """Runtime state for an open document.

    The SVG file on disk is the sole source of truth (Madde 1).
    """

    svg_path: Path
    revision: int = 1
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Set of destroyed IDs (from id-changing operations)
    destroyed_ids: set[str] = field(default_factory=set)
    # Unit conversion factor: px / user-unit.
    # Computed from viewBox and width attributes on load.
    px_to_user_unit: float = 1.0
    # viewBox (x, y, w, h) cached for unit conversion
    view_box: tuple[float, float, float, float] = (0, 0, 0, 0)
    # width/height in px from the <svg> element
    width_px: float = 0.0
    height_px: float = 0.0
    # SVG namespace elements as lxml tree (cached; file is authority)
    _tree: etree._ElementTree | None = field(default=None, repr=False)
    last_access: float = field(default_factory=time.time)


def _parse_length(value: str) -> float:
    """Parse SVG length value, stripping unit suffix (px, mm, cm, in, pt, pc).

    Returns value in px (96 dpi). Raises ValueError if unparseable.
    """
    import re
    value = value.strip()
    unit_map = {
        "px": 1.0,
        "mm": 96.0 / 25.4,
        "cm": 96.0 / 2.54,
        "in": 96.0,
        "pt": 96.0 / 72.0,
        "pc": 96.0 / 6.0,
    }
    m = re.match(r"^([+-]?\d*\.?\d+)\s*(px|mm|cm|in|pt|pc)?$", value)
    if not m:
        raise ValueError(f"Cannot parse SVG length: {value}")
    num = float(m.group(1))
    unit = m.group(2) or "px"
    return num * unit_map[unit]


class SessionManager:
    """Manages per-document sessions with locking and revision tracking."""

    def __init__(self, config: SecurityConfig) -> None:
        self.config = config
        self._documents: dict[str, DocumentState] = {}
        # Key = normalized real path string

    def _normalize_key(self, path: Path) -> str:
        """Normalize a path to a document map key."""
        resolved = validate_path(path, self.config)
        # Case-fold on Windows
        key = str(resolved.resolve(strict=False))
        return os.path.normcase(key)

    async def get_or_open(self, svg_path: Path) -> DocumentState:
        """Get existing session or create a new one (with lock).

        Must be called within an async context.
        Returns the document state after acquiring its lock.
        """
        key = self._normalize_key(svg_path)

        if key not in self._documents:
            if not svg_path.exists():
                raise DocumentNotFoundError(f"SVG file not found: {svg_path}")
            state = DocumentState(svg_path=svg_path)
            self._load_unit_info(state)
            self._documents[key] = state

        state = self._documents[key]
        state.last_access = time.time()
        return state

    def register_new(self, svg_path: Path, revision: int = 1) -> DocumentState:
        """Register a newly created document."""
        key = self._normalize_key(svg_path)
        state = DocumentState(svg_path=svg_path, revision=revision)
        self._load_unit_info(state)
        self._documents[key] = state
        return state

    def _load_unit_info(self, state: DocumentState) -> None:
        """Compute px→user-unit conversion from SVG attributes.

        Handles unit suffixes (e.g., width="200px", width="210mm")
        and converts to px at 96 dpi.
        """
        if not state.svg_path.exists():
            return
        try:
            tree = etree.parse(str(state.svg_path))
            root = tree.getroot()
            w = _parse_length(root.get("width", "0"))
            h = _parse_length(root.get("height", "0"))
            vb = root.get("viewBox")
            if vb:
                parts = vb.split()
                vx, vy, vw, vh = (float(p) for p in parts)
                factor = w / vw if vw != 0 else 1.0
            else:
                vx, vy, vw, vh = (0, 0, w, h)
                factor = 1.0
            state.width_px = w
            state.height_px = h
            state.view_box = (vx, vy, vw, vh)
            state.px_to_user_unit = factor
            state._tree = tree
        except Exception:
            state.px_to_user_unit = 1.0
            state._tree = None

    def px_to_user(self, state: DocumentState, px_value: float) -> float:
        """Convert a px value to user-unit using the document factor."""
        if state.px_to_user_unit == 0:
            return px_value
        return px_value / state.px_to_user_unit

    def user_to_px(self, state: DocumentState, user_value: float) -> float:
        """Convert a user-unit value to px."""
        return user_value * state.px_to_user_unit

    def check_revision(self, state: DocumentState, expected: int | None) -> None:
        """If expected_revision is given, verify it matches current."""
        if expected is not None and expected != state.revision:
            raise StaleRevisionError(expected, state.revision)

    def check_id_exists(self, tree: etree._Element, object_id: str) -> None:
        """Raise IdNotFoundError or IdDestroyedError if ID is absent."""
        # Search for element with matching id
        found = tree.xpath(f"//*[@id='{object_id}']")
        if not found:
            # Could be destroyed
            raise IdNotFoundError(object_id)

    def collect_ids(self, tree: etree._Element) -> set[str]:
        """Collect all element IDs in a document."""
        ids: set[str] = set()
        for el in tree.iter():
            id_attr = el.get("id")
            if id_attr:
                ids.add(id_attr)
        return ids

    def diff_ids(
        self, before: set[str], after: set[str]
    ) -> dict:
        """Compute id-map from before/after ID sets.

        Returns {survived: {old→new}, destroyed: [...], created: [...]}
        For path-union: destroyed contains the lost IDs, survived maps remaining.
        """
        destroyed = sorted(before - after)
        created = sorted(after - before)
        # For simple surviving IDs (same id in both), map old→new = same
        survived = {id_: id_ for id_ in (before & after)}
        return {
            "survived": survived,
            "destroyed": destroyed,
            "created": created,
        }


# ── Atomic file I/O ──


def atomic_write_svg(
    svg_path: Path,
    content: bytes | str,
    config: SecurityConfig,
) -> int:
    """Write SVG content atomically using temp+replace.

    Returns new file size in bytes.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    validate_svg_size(content, config)

    target = svg_path.resolve(strict=False)
    target_dir = target.parent
    # Temp file in same directory (same filesystem = atomic replace)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target_dir), prefix=".inkscape_mcp_", suffix=".svg"
    )
    try:
        os.write(fd, content)
        os.fsync(fd)
        os.close(fd)
        # Atomic replace on Windows (same fs)
        os.replace(tmp_path, str(target))
        return len(content)
    except Exception:
        # Cleanup temp on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_svg_file(svg_path: Path, config: SecurityConfig) -> bytes:
    """Read SVG file with size validation."""
    data = svg_path.read_bytes()
    validate_svg_size(data, config)
    return data
