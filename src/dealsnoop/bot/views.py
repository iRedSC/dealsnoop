"""Discord views (buttons, etc.) for search posts."""

from __future__ import annotations

import discord  # type: ignore[import-untyped]

MAX_EMBED_DESC = 4096


class ThoughtTraceView(discord.ui.View):
    """View with a button that shows the AI's thought trace for a listing."""

    def __init__(self, thought_trace: str, *, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.thought_trace = thought_trace.strip() or "(No thought trace available)"

    @discord.ui.button(label="Show AI reasoning", style=discord.ButtonStyle.secondary, custom_id="thought_trace")
    async def show_thought_trace(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        text = self.thought_trace
        if len(text) > MAX_EMBED_DESC:
            text = text[: MAX_EMBED_DESC - 3] + "..."
        embed = discord.Embed(
            title="AI thought trace",
            description=text,
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
