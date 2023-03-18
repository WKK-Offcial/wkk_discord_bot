from __future__ import annotations
import logging
import sys
from typing import TYPE_CHECKING, Literal, Optional
import discord
from discord.ext import commands
from discord.ext.commands import Greedy, Context

if TYPE_CHECKING:
  from main import BoiBot


class BotAdmin(commands.Cog):
  """
  Class used for controlling the bot as admin
  """
  def __init__(self, bot:BoiBot) -> None:
    super().__init__()
    self.bot:BoiBot = bot


  # Implement meta functions
    @self.bot.command()
    @commands.guild_only()
    async def sync(ctx: Context,
          guilds: Greedy[discord.Object],
          spec: Optional[Literal["~", "*", "^"]] = None) -> None:
      """
      This command sync slash commands with discord
      """
      if not guilds:
        if spec == "~":
          synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
          ctx.bot.tree.copy_global_to(guild=ctx.guild)
          synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
          ctx.bot.tree.clear_commands(guild=ctx.guild)
          await ctx.bot.tree.sync(guild=ctx.guild)
          synced = []
        else:
          synced = await ctx.bot.tree.sync()

        is_spec = 'globally' if spec is None else 'to the current guild.'
        await ctx.send(
          f"Synced {len(synced)} commands {is_spec}"
        )
        return

      ret = 0
      for guild in guilds:
        try:
          await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException:
          pass
        else:
          ret += 1

      await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

    @self.bot.command()
    @commands.guild_only()
    async def restart(ctx: Context) -> None:
      """
      This command sync slash commands with discord
      """
      logging.warning('Restart called from %d', ctx.guild.id)
      sys.exit()
