import asyncio
import os
import logging
from dotenv import load_dotenv
import discord
import static_ffmpeg
from cogs.audio_player import AudioPlayer
from cogs.bot_admin import BotAdmin
from utils.boi_bot import BoiBot

# Set up logger
logging.basicConfig(level=logging.INFO)
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

bot = BoiBot()
@bot.event
async def on_ready():
  """
  Event that ocuurence one time when bot is ready to work
  """
  logging.info('Logged in as %s (ID: %d)\n-----------\n', bot.user, bot.user.id)



async def main():
  """Main boot start function"""
  discord.utils.setup_logging(level=logging.WARNING, root=False)
  async with bot:
    await bot.add_cog(BotAdmin(bot))
    await bot.add_cog(AudioPlayer(bot))
    await bot.start(os.getenv('BOT_TOKEN'))


asyncio.run(main())
