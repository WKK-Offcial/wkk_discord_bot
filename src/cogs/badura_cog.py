from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from __main__ import DiscordBot


class BaduraCog(commands.Cog):
    """
    Class for commands related with Badura
    """

    def __init__(self, bot: DiscordBot) -> None:
        super().__init__()
        self.bot: DiscordBot = bot

    @app_commands.command(name="wypomnienie")
    async def update_rebuke(self, interaction: discord.Interaction) -> None:
        """
        Update wypomnienie
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("./soundboards/wypomnienie.txt", "w+") as file:
            file.write(timestamp)
        await interaction.response.send_message("Wypomnienie zostało zaktualizowane.")

    @app_commands.command(name="kiedy_wypomnienie")
    async def get_last_rebuke(self, interaction: discord.Interaction) -> None:
        """
        Command to get last wypomnienie
        """
        with open("./soundboards/wypomnienie.txt", "r") as file:
            last_rebuke = file.read()
        last_rebuke_time = datetime.strptime(last_rebuke, "%Y-%m-%d %H:%M:%S")
        time_difference = datetime.now() - last_rebuke_time
        await interaction.response.send_message(
            f"""Ostatnie wypomnienie było {time_difference.days} dni, {time_difference.seconds // 3600} 
            godzin i {time_difference.seconds % 3600 // 60} minut temu."""
        )
