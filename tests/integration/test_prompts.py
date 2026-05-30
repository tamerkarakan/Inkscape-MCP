class TestVectorizeImagePrompt:
    """Verify the vectorize_image prompt is registered and renders correctly."""

    async def test_prompt_registered(self):
        """vectorize_image is listed with expected arguments."""
        from inkscape_mcp.server import create_server
        server = create_server()

        prompts = await server.list_prompts()
        found = [p for p in prompts if p.name == "vectorize_image"]
        assert len(found) == 1, "vectorize_image prompt not found"
        prompt = found[0]
        arg_names = {a.name for a in (prompt.arguments or [])}
        assert arg_names == {"document_path", "instructions"}

    async def test_render_interpolates_args(self):
        """Provided args appear in the rendered text with required keywords."""
        from inkscape_mcp.server import create_server
        server = create_server()

        res = await server.get_prompt(
            "vectorize_image",
            {"document_path": "logo.svg", "instructions": "flat 2-color"},
        )
        full_text = "".join(getattr(m.content, "text", "") for m in res.messages)
        assert "logo.svg" in full_text
        assert "flat 2-color" in full_text
        assert "element_create" in full_text
        assert "trace-bitmap" in full_text

    async def test_empty_args_use_document_create(self):
        """Empty arguments route to document_create and still mention trace-bitmap."""
        from inkscape_mcp.server import create_server
        server = create_server()

        res = await server.get_prompt("vectorize_image", {})
        full_text = "".join(getattr(m.content, "text", "") for m in res.messages)
        assert "document_create" in full_text
        assert "trace-bitmap" in full_text
