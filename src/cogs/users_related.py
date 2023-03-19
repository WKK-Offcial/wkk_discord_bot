from __future__ import annotations
from typing import TYPE_CHECKING
import discord
from discord.ext import commands
from discord import app_commands


if TYPE_CHECKING:
  from main import BoiBot

class UsersRelated(commands.Cog):
  """
  Class for commands realted with users
  """
  def __init__(self, bot:BoiBot) -> None:
    super().__init__()
    self.bot:BoiBot = bot

  @app_commands.command(name="avatar")
  async def avatar(self, interaction: discord.Interaction, member: discord.Member = None) -> None:
    """
    Command to get user avatar
    """
    avatar_url = member.avatar.url
    embed = discord.Embed()
    embed.set_image(url=avatar_url)
    await interaction.response.send_message(embed = embed)
