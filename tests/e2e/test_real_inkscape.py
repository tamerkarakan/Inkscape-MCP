"""
End-to-end tests using the REAL Inkscape 1.4.2 binary.

These tests are skipped unless INKSCAPE_BIN is set in environment.
Requires: INKSCAPE_BIN pointing to inkscape.com (Windows) or inkscape (Linux).

Tests verify:
  - F4: DOM element creation (no CLI for geometry)
  - F5: query-returns-px → user-unit conversion
  - F8: path-union destroys operand IDs (id-map)
  - F9: transform-translate bakes into x/y (no transform attr)
  - F7: selection-based actions (select-by-id replay)
  - Export PNG/SVG works headless
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

# Skip entire module if no Inkscape binary
pytestmark = pytest.mark.e2e

INKSCAPE_BIN = os.environ.get("INKSCAPE_BIN")
if not INKSCAPE_BIN:
    pytest.skip("INKSCAPE_BIN not set", allow_module_level=True)


@pytest.fixture
def inkscape_workspace(tmp_path):
    """Workspace with copies of reference fixtures."""
    fixtures = Path(__file__).parent.parent.parent / "reference" / "fixtures"
    ws = tmp_path / "workspace"
    ws.mkdir()

    # Copy base input
    shutil.copy(fixtures / "base-input.svg", ws / "input.svg")
    return ws


# ── F4: DOM element creation (no Inkscape CLI for geometry) ──


def test_dom_element_create_rect(inkscape_workspace):
    """F4: Create a rect via DOM — never through Inkscape CLI."""
    from lxml import etree
    from inkscape_mcp.session import atomic_write_svg
    from inkscape_mcp.security import SecurityConfig

    config = SecurityConfig(workspace_root=inkscape_workspace)

    svg_path = inkscape_workspace / "dom_create.svg"
    svg_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">'
        '<defs id="defs1"/></svg>'
    )
    atomic_write_svg(svg_path, svg_content, config)

    # Parse, add rect element
    tree = etree.parse(str(svg_path))
    root = tree.getroot()
    ns = "http://www.w3.org/2000/svg"
    elem = etree.SubElement(root, f"{{{ns}}}rect")
    elem.set("id", "newrect")
    elem.set("x", "5")
    elem.set("y", "5")
    elem.set("width", "20")
    elem.set("height", "20")
    elem.set("fill", "magenta")

    new_svg = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    atomic_write_svg(svg_path, new_svg, config)

    # Verify the new element exists (property assertion, not byte-snapshot)
    tree2 = etree.parse(str(svg_path))
    found = tree2.xpath("//*[@id='newrect']")
    assert len(found) == 1
    assert found[0].get("fill") == "magenta"
    assert found[0].tag == f"{{{ns}}}rect"


# ── F5: query px → user-unit conversion ──


def test_query_returns_px_converted_to_user_unit(inkscape_workspace):
    """F5/Madde 15: --query-all returns px; server converts to user-unit.

    base-input.svg has width=200, viewBox=0 0 200 200 → factor=1.0
    r1 x=10 should report 10 in user-unit.
    """
    import subprocess

    svg_path = inkscape_workspace / "input.svg"
    result = subprocess.run(
        [INKSCAPE_BIN, "--query-all", str(svg_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0

    # Parse raw output (px)
    lines = result.stdout.strip().splitlines()
    rects = [line for line in lines if "r1" in line]
    assert len(rects) == 1
    # r1,x,y,w,h in px
    parts = rects[0].split(",")
    px_x = float(parts[1])
    px_y = float(parts[2])

    # base-input has factor=1.0, so px=user-unit
    assert px_x == 10.0
    assert px_y == 10.0

    # Verify our normalization layer
    from inkscape_mcp.normalize import normalize_query_all
    objs = normalize_query_all(result.stdout)
    r1 = [o for o in objs if o["id"] == "r1"][0]
    assert r1["x"] == 10.0
    assert r1["y"] == 10.0
    assert r1["width"] == 50.0
    assert r1["height"] == 40.0


def test_query_all_ids_present(inkscape_workspace):
    """Verify base-input.svg has r1, c1, p1."""
    import subprocess

    svg_path = inkscape_workspace / "input.svg"
    result = subprocess.run(
        [INKSCAPE_BIN, "--query-all", str(svg_path)],
        capture_output=True, text=True, timeout=30,
    )
    lines = result.stdout.strip().splitlines()
    ids = [line.split(",")[0] for line in lines]
    assert "r1" in ids
    assert "c1" in ids
    assert "p1" in ids


# ── F8: path-union destroys operand IDs ──


def test_path_union_id_behavior(inkscape_workspace):
    """F8: path-union merges r1+c1 into single <path>; c1 is destroyed.

    This is the CRITICAL test for id-map (Madde 14).
    """
    import subprocess
    from lxml import etree

    svg_path = inkscape_workspace / "input_union.svg"
    shutil.copy(inkscape_workspace / "input.svg", svg_path)

    # Collect IDs before
    tree_before = etree.parse(str(svg_path))
    {el.get("id") for el in tree_before.iter() if el.get("id")}

    # Run: object-to-path(r1), object-to-path(c1), path-union
    # Per F7: must select-by-id before each action
    # --actions doesn't write back; must export to save result (F19)
    out_path = inkscape_workspace / "output_union.svg"
    actions = (
        "select-clear;select-by-id:r1;object-to-path;"
        "select-clear;select-by-id:c1;object-to-path;"
        "select-clear;select-by-id:r1;select-by-id:c1;path-union;"
        f"export-filename:{out_path};export-type:svg;export-do"
    )
    subprocess.run(
        [INKSCAPE_BIN, f"--actions={actions}", str(svg_path)],
        capture_output=True, text=True, timeout=30,
    )

    # Collect IDs after from EXPORTED file
    tree_after = etree.parse(str(out_path))
    ids_after = {el.get("id") for el in tree_after.iter() if el.get("id")}

    # c1 should be DESTROYED (F8)
    assert "c1" not in ids_after, f"c1 should be destroyed, found ids: {ids_after}"
    # r1 should SURVIVE (en alttaki operandın id'si kalır)
    assert "r1" in ids_after, f"r1 should survive, found ids: {ids_after}"
    # p1 untouched
    assert "p1" in ids_after

    # r1 should now be a <path> element (not <rect>)
    r1_elem = tree_after.xpath("//*[@id='r1']")[0]
    assert "path" in r1_elem.tag.lower(), f"r1 should be <path>, got {r1_elem.tag}"
    assert r1_elem.get("d") is not None, "r1 should have a 'd' attribute"


# ── F9: transform-translate bakes into x/y ──


def test_transform_translate_bakes_xy(inkscape_workspace):
    """F9: transform-translate updates x/y directly, NO transform attr."""
    import subprocess
    from lxml import etree

    svg_path = inkscape_workspace / "input_translate.svg"
    shutil.copy(inkscape_workspace / "input.svg", svg_path)

    out_path = inkscape_workspace / "output_translate.svg"
    actions = (
        "select-clear;select-by-id:r1;transform-translate:100,0;"
        f"export-filename:{out_path};export-type:svg;export-do"
    )
    subprocess.run(
        [INKSCAPE_BIN, f"--actions={actions}", str(svg_path)],
        capture_output=True, text=True, timeout=30,
    )

    tree = etree.parse(str(out_path))
    r1 = tree.xpath("//*[@id='r1']")[0]

    # x should be 110 (was 10, translated by 100)
    assert r1.get("x") == "110", f"Expected x=110, got {r1.get('x')}"
    # y unchanged
    assert r1.get("y") == "10"
    # NO transform attribute (F9)
    assert r1.get("transform") is None, f"transform attr should not exist, got {r1.get('transform')}"


# ── F7: selection-based actions ──


def test_set_attribute_selection_based(inkscape_workspace):
    """F7: object-set-attribute must be preceded by select-by-id."""
    import subprocess
    from lxml import etree

    svg_path = inkscape_workspace / "input_fill.svg"
    shutil.copy(inkscape_workspace / "input.svg", svg_path)

    # Correct: select-by-id BEFORE set-attribute; must export to save (F19)
    out_path = inkscape_workspace / "output_fill.svg"
    actions = (
        "select-clear;select-by-id:r1;object-set-attribute:fill,purple;"
        f"export-filename:{out_path};export-type:svg;export-do"
    )
    subprocess.run(
        [INKSCAPE_BIN, f"--actions={actions}", str(svg_path)],
        capture_output=True, text=True, timeout=30,
    )

    tree = etree.parse(str(out_path))
    r1 = tree.xpath("//*[@id='r1']")[0]
    assert r1.get("fill") == "purple"


# ── Export tests ──


def test_export_png(inkscape_workspace):
    """Export SVG to PNG headless."""
    import subprocess

    svg_path = inkscape_workspace / "input.svg"
    png_path = inkscape_workspace / "output.png"

    actions = f"export-filename:{png_path};export-type:png;export-do"
    result = subprocess.run(
        [INKSCAPE_BIN, f"--actions={actions}", str(svg_path)],
        capture_output=True, text=True, timeout=60,
    )

    assert png_path.exists(), f"PNG not created. stderr: {result.stderr[:500]}"
    assert png_path.stat().st_size > 0


def test_export_svg_plain(inkscape_workspace):
    """Export to plain SVG (no Inkscape namespaces)."""
    import subprocess

    svg_path = inkscape_workspace / "input.svg"
    out_path = inkscape_workspace / "output_plain.svg"

    actions = f"export-filename:{out_path};export-type:svg;export-plain-svg;export-do"
    subprocess.run(
        [INKSCAPE_BIN, f"--actions={actions}", str(svg_path)],
        capture_output=True, text=True, timeout=30,
    )

    assert out_path.exists()
    content = out_path.read_text()
    assert "<svg" in content


# ── Shell mode test (F10) ──


def test_shell_session_state_persistence(inkscape_workspace):
    """F10: --shell maintains document state across commands."""
    import subprocess

    svg_path = inkscape_workspace / "input_shell.svg"
    shutil.copy(inkscape_workspace / "input.svg", svg_path)

    commands = (
        f"file-open:{svg_path}\n"
        "select-by-id:c1\n"
        "object-set-attribute:fill,orange\n"
        "query-all\n"
        "quit\n"
    )

    result = subprocess.run(
        [INKSCAPE_BIN, "--shell"],
        input=commands,
        capture_output=True, text=True,
        timeout=30,
    )

    # The shell output should contain c1 data (state preserved)
    # And the fill change should be reflected in query output
    assert "c1" in result.stdout


# ── T-4: PDF export + path_difference E2E ──


def test_export_pdf(inkscape_workspace):
    """Export SVG to PDF headless."""
    import subprocess

    svg_path = inkscape_workspace / "input.svg"
    pdf_path = inkscape_workspace / "output.pdf"

    # PDF export uses --export-filename + --export-type (no export-do needed)
    result = subprocess.run(
        [
            INKSCAPE_BIN,
            f"--export-filename={pdf_path}",
            "--export-type=pdf",
            str(svg_path),
        ],
        capture_output=True, text=True, timeout=60,
    )

    assert pdf_path.exists(), f"PDF not created. stderr: {result.stderr[:500]}"
    assert pdf_path.stat().st_size > 0


def test_path_difference_operation(inkscape_workspace):
    """Path difference: r1 minus c1, verify c1 is destroyed."""
    import subprocess
    from lxml import etree

    import shutil
    svg_path = inkscape_workspace / "input_diff.svg"
    shutil.copy(inkscape_workspace / "input.svg", svg_path)

    out_path = inkscape_workspace / "output_diff.svg"
    # Per-operand pattern: object-to-path each operand, then path-difference
    actions = (
        "select-clear;select-by-id:r1;object-to-path;"
        "select-clear;select-by-id:c1;object-to-path;"
        "select-clear;select-by-id:r1;select-by-id:c1;path-difference;"
        f"export-filename:{out_path};export-type:svg;export-do"
    )
    subprocess.run(
        [INKSCAPE_BIN, f"--actions={actions}", str(svg_path)],
        capture_output=True, text=True, timeout=30,
    )

    assert out_path.exists(), "Path-difference output not created"

    tree = etree.parse(str(out_path))
    ids_after = {el.get("id") for el in tree.iter() if el.get("id")}

    # r1 should survive (bottom operand)
    assert "r1" in ids_after, f"r1 should survive, got {ids_after}"
    # p1 untouched
    assert "p1" in ids_after
    # c1 is cut away
    assert "c1" not in ids_after, f"c1 should be destroyed by path-difference, got {ids_after}"

    # r1 should now be a path element
    r1_elem = tree.xpath("//*[@id='r1']")[0]
    assert "path" in r1_elem.tag.lower()
