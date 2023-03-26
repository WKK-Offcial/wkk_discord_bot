import asyncio
import logging
import os
import sentry_sdk

import discord
import static_ffmpeg
import wavelink
from dotenv import load_dotenv

from cogs.audio_player import AudioPlayer
from cogs.bot_admin import BotAdmin
from cogs.users_related import UsersRelated
from utils.discord_bot import DiscordBot
from views.audio_player_view import PlayerControlView

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

if key := os.getenv("SENTRY_KEY", None):
    sentry_sdk.init(
      dsn=key,
      # Set tracesSampleRate to 1.0 to capture 100%
      # of transactions for performance monitoring.
      # We recommend adjusting this value in production
      traces_sample_rate=1.0,
      _experiments={
            "profiles_sample_rate": 1.0,
        }
    )


# Create bot and cogs
bot = DiscordBot()
bot_admin = BotAdmin(bot)
audio_player = AudioPlayer(bot)
users_related = UsersRelated(bot)


# Setup events
@bot.event
async def on_ready():
    """
    Event that occurrence one time when bot is ready to work
    """
    logging.info('Logged in as %s (ID: %d)\n-----------\n', bot.user, bot.user.id)


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """
    Event that occurrence whenever someone leaves/joins vc
    """
    voice_state = member.guild.voice_client
    # Checking if the bot is connected to a channel and if there is only 1 member connected to it (the bot itself)
    if voice_state is not None and len(voice_state.channel.members) == 1:
        state: PlayerControlView = audio_player.views.get(member.guild.id)
        bot_vc: wavelink.Player = member.guild.voice_client
        if bot_vc.is_playing():
            bot_vc.queue.clear()
            await bot_vc.stop()
        await state.transit_to_stopped_no_users()
        await voice_state.disconnect()


async def main():
    """
    Main boot start function
    """
    discord.utils.setup_logging(level=logging.WARNING, root=False)
    # Load cogs
    async with bot:
        await bot.add_cog(bot_admin)
        await bot.add_cog(users_related)
        await bot.add_cog(audio_player)
        await bot.start(os.getenv('BOT_TOKEN'))

asyncio.run(main())
