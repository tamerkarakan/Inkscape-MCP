# Inkscape MCP Server

> A **Model Context Protocol (MCP)** server that lets AI assistants create, edit, query, and export **SVG graphics through Inkscape 1.4.2** — designed to work even for *small, weak local models*, not just frontier ones.

The goal is simple: a non-expert can ask an AI assistant for "a clean coffee-shop logo with warm colors," and the assistant builds it element-by-element in real Inkscape, previews it, and exports it — without the user touching the SVG XML.

---

## Why this exists

Most "AI → vector graphics" tools assume a powerful model with a huge context window. This server is built around the opposite assumption: **the client model may be weak** (e.g. a 4-bit quantized 7B model running locally). So the protocol does the heavy lifting:

- **Self-documenting tools** — every tool description carries the schema, units, and examples a model needs, so a black-box client never has to read the source.
- **Small, structured I/O** — tools return typed payloads, not walls of text.
- **`element_create` as the accessibility core** — one well-described tool can author rects, circles, ellipses, paths, and text, so even a model that can't write raw SVG can produce real geometry.
- **Server-enforced quality gate** — the server can *refuse to export* an empty or near-empty canvas, nudging the agent to actually review its work first (see [Review Gate](#review-gate)).

---

## Status

⚠️ **Early / experimental.** Core authoring, query, preview, export, review-gate, and multi-client workspace isolation work and are covered by tests. APIs and tool names may still change. This is not production-hardened software — see the [Disclaimer](#disclaimer).

- **Inkscape:** 1.4.2 (portable, Windows x64 verified; Linux/macOS expected to work via the `inkscape` CLI)
- **Python:** ≥ 3.11
- **MCP SDK:** `mcp` (official Python SDK)
- **Transports:** stdio (default), SSE, Streamable HTTP

---

## Supported clients

| Client | Transport | Notes |
|---|---|---|
| **Claude Desktop** | stdio | Spawns the server as a local process. Primary target. |
| **LM Studio + local models** (e.g. `qwen2.5-instruct`) | stdio | Validated: a 4-bit quant *can* drive the tools and emit valid SVG. Output quality tracks model capability. |
| **ChatGPT (Developer Mode)** | Streamable HTTP (`/mcp`) | Requires a public tunnel (e.g. cloudflared) + DNS-rebinding protection disabled for the tunnel host. |
| **Any MCP client** | stdio / SSE / HTTP | Standard MCP — should work with any conformant client. |

### Multi-client workspace isolation
When several clients connect (Claude + a local model + ChatGPT), they used to collide by writing files with the same name into one shared folder. The server now **auto-isolates each client** into its own subdirectory under a single workspace root, derived from the client's `clientInfo.name` from the MCP handshake — no per-client hard-coding required. ChatGPT, LM Studio, and Claude each get their own folder automatically.

---

## Supported tools

**21 tools**, grouped by purpose. (Units are Inkscape user units unless noted.)

### Authoring
| Tool | What it does |
|---|---|
| `document_create` | Create a new SVG document with given canvas size. |
| `element_create` | Create one SVG element (`rect`, `circle`, `ellipse`, `path`, `text`) and return its id. Paint/style keys (`fill`, `stroke`, `stroke_width`, `opacity`, …) work on any type; unknown keys pass straight through to SVG attributes. Supports `before_id` to insert beneath an existing element. |
| `element_update` | Update attributes / style of an existing element. |
| `write_svg` | Write a full raw SVG document (escape hatch for capable models). |
| `transform_element` | Translate, scale, rotate, skew, or apply an affine matrix. |
| `reorder_element` | Change z-order (raise / lower / to-top / to-bottom / before a given id). |
| `create_gradient` | Create a linear or radial gradient; returns a `url(#id)` usable as a fill/stroke. |
| `create_pattern` | Create a pattern fill; returns a `url(#id)`. |

### Query & review
| Tool | What it does |
|---|---|
| `query_geometry` | Bounding boxes (x, y, w, h) for one or all objects. |
| `review_design` | Heuristic design critique — element/color counts, coverage %, and flags (empty, very sparse, single-color, no-text, …). Backs the [Review Gate](#review-gate). |
| `workspace_info` | Report the active (per-client) workspace path. |

### Render & export
| Tool | What it does |
|---|---|
| `render_preview` | Render a PNG preview (base64) of the current document. |
| `export_document` | Export to PNG / PDF / etc. **Gated** by `review_design` when enabled. |
| `run_actions` | Run a raw Inkscape `--actions` chain (advanced escape hatch). |

### Image → vector
| Tool | What it does |
|---|---|
| `import_image` | Embed/link a raster image (file path or base64 `image_data`). |
| `trace_bitmap` | Dumb bitmap auto-trace — the *fallback*, not the primary path. |

> **Image-to-vector philosophy:** AI *reconstruction* (the client model understanding the image and rebuilding it with semantic elements) is the primary path; `trace_bitmap` is the dumb fallback. The `vectorize_image` prompt teaches the client this distinction.

### GUI session (opt-in)
| Tool | What it does |
|---|---|
| `gui_open` / `gui_apply` / `gui_export` / `gui_close` | Drive a persistent Inkscape GUI session for actions that need a live canvas. |

### Interaction
| Tool | What it does |
|---|---|
| `ask_user` | Elicit a clarifying answer from the user mid-task (MCP elicitation). |

### Resources & prompts
- **Resources:** `inkscape://session/capabilities`, `…/document-info/{path}`, `…/svg/{path}`, `…/preview/{path}`, `…/list`
- **Prompts:** `vectorize_image` — "Convert an uploaded image to clean, semantic SVG using AI understanding, not trace-bitmap."

---

## Review Gate

MCP can't force a model to *reason*, but it **can** gate an action on server state. When `require_review_before_export` is enabled, `export_document` checks whether the current document revision has actually been reviewed. If `review_design` reports a blocking flag (e.g. `empty_document`, `mostly_empty_canvas`), the export is **refused** with an explanation.

This was added after observing that a capable client claimed to have "reviewed" a design it never actually inspected. The gate checks **server state, not the agent's claim** — there is no client exemption. Clean designs pass automatically; only genuinely empty/near-empty output is blocked.

---

## Quick start (stdio, e.g. Claude Desktop)

```json
{
  "mcpServers": {
    "inkscape": {
      "command": "python",
      "args": ["-m", "inkscape_mcp.server"],
      "env": {
        "INKSCAPE_BIN": "C:/path/to/inkscape/bin/inkscape.com",
        "INKSCAPE_WORKSPACE": "C:/Users/you/InkscapeDesigns"
      }
    }
  }
}
```

### HTTP / ChatGPT
Set the transport and (for a public tunnel) disable DNS-rebinding protection:

```
INKSCAPE_MCP_TRANSPORT=streamable-http
INKSCAPE_MCP_HOST=127.0.0.1
INKSCAPE_MCP_PORT=8000
```

Then expose `http://127.0.0.1:8000/mcp` through a tunnel (e.g. `cloudflared tunnel --url http://127.0.0.1:8000`) and point the ChatGPT connector at `https://<your-tunnel>/mcp`.

> ⚠️ A public tunnel with no authentication means **anyone with the URL can drive your machine's Inkscape**. Use it only for testing, and shut the tunnel down when done.

---

## Roadmap / TODO

- [x] Core authoring tools (`document_create`, `element_create`, `element_update`, transforms, z-order)
- [x] Gradients & patterns
- [x] Query geometry, PNG preview, multi-format export
- [x] AI-first image vectorization + `trace_bitmap` fallback
- [x] Self-documenting tool schemas (no source-peeking for weak clients)
- [x] Auto workspace isolation per MCP client identity
- [x] Server-enforced review gate before export
- [x] Optional SSE / Streamable HTTP transport (ChatGPT support)
- [ ] **Per-session** workspace binding for HTTP (currently bind-once-per-process; fine for single-user, not multi-tenant)
- [ ] Friendly-name mapping for verbose `clientInfo.name` values
- [ ] Optional OAuth / token auth for HTTP transport
- [ ] Cross-platform CI (Windows + Linux + macOS) against a real Inkscape binary
- [ ] Richer review heuristics (contrast, overlap, off-canvas detection)
- [ ] More authoring primitives (polygon/star/spiral convenience wrappers)
- [ ] Published package / one-click installer

---

## Architecture (short version)

```
MCP Client (Claude / LM Studio / ChatGPT)
      │  JSON-RPC over stdio | SSE | Streamable HTTP
      ▼
Inkscape MCP Server (Python, FastMCP)
      ├─ per-client workspace isolation
      ├─ review gate (server state, not agent claims)
      ├─ DOM authoring via lxml
      └─ Inkscape CLI (--query-all, export, actions) + optional GUI session
```

The original, longer design document lives at [`docs/DESIGN.md`](docs/DESIGN.md). Note it is an early aspirational spec; this README reflects what is actually implemented.

---

## Security notes

- File access is confined to the configured workspace root (per-client subdirectory).
- No shell execution; Inkscape is invoked with explicit arguments.
- Export formats and document sizes are bounded.
- HTTP transport without auth is **not** safe to expose publicly — see the tunnel warning above.

---

## Disclaimer

**This software is provided "AS IS", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. In no event shall the authors or copyright holders be liable for any claim, damages, or other liability, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the software or the use or other dealings in the software.**

Additional, project-specific cautions:

- **Experimental software.** This is an early-stage, hobby/research project. It may contain bugs, may corrupt or overwrite files within its workspace, and may behave unexpectedly. Do not point it at directories containing data you cannot afford to lose. Keep backups.
- **AI-generated output.** Graphics produced through this server are generated by AI models and may be inaccurate, low-quality, or unsuitable for any particular use. You are responsible for reviewing all output before use.
- **You run untrusted instructions.** When you connect an MCP client, the connected AI model can create, modify, and delete files inside the workspace, and invoke Inkscape on your machine. Only connect clients and models you trust.
- **Network exposure.** The optional HTTP/SSE transports, especially when exposed through a public tunnel **without authentication**, allow anyone who knows the URL to operate Inkscape on your machine. This is intended for local testing only. Securing, authenticating, and firewalling any network-exposed deployment is entirely your responsibility.
- **Third-party software.** Inkscape, the MCP SDK, and any AI models or services you connect are governed by their own licenses and terms; this project does not grant rights to, and is not affiliated with, any of them. "Inkscape" is a trademark of its respective owners; this project is an independent integration and is not endorsed by or affiliated with the Inkscape project.
- **No professional advice or guarantees.** Nothing here is a guarantee of correctness, security, availability, or fitness for any task.

Use at your own risk.

---

## License

[MIT](LICENSE) — see the disclaimer above. Open-source, compatible with the Inkscape community.
