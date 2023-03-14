import asyncio
from typing import Literal, Optional
import os
import logging
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord.ext.commands import Greedy, Context
import static_ffmpeg
from cogs.audio_player import AudioPlayer


# Load env variables from .env file
load_dotenv()
# Load static ffmpeg library
static_ffmpeg.add_paths()
# Load opus library - depends on OS
if os.name == 'nt':
  discord.opus._load_default()
elif os.name == 'posix':
  discord.opus.load_opus('libopus.so.0')
if not discord.opus.is_loaded():
  raise RuntimeError('Opus failed to load!')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
  command_prefix=commands.when_mentioned_or("/"),
  description='The Boi is back',
  intents=intents,
)

@bot.event
async def on_ready():
  """Event that ocuurence one time when bot is ready to work"""
  print(f'Logged in as {bot.user} (ID: {bot.user.id})')
  print('------')


@bot.command()
@commands.guild_only()
async def sync(ctx: Context,
      guilds: Greedy[discord.Object],
      spec: Optional[Literal["~", "*", "^"]] = None) -> None:
  """This command sync slash commands with discord"""
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


async def main():
  """Main boot start function"""
  discord.utils.setup_logging(level=logging.DEBUG, root=False)
  async with bot:
    await bot.add_cog(AudioPlayer(bot))
    await bot.start(os.getenv('BOT_TOKEN'))


asyncio.run(main())
