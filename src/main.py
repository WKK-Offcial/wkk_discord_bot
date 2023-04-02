import asyncio
import logging
import os
import sys

import discord
import sentry_sdk
import static_ffmpeg
from dotenv import load_dotenv

from cogs.audio_player import AudioPlayer
from cogs.bot_admin import BotAdmin
from cogs.users_related import UsersRelated
from utils.discord_bot import DiscordBot

# Set up logger
logging.basicConfig(level=logging.INFO, format="[%(module)s][%(funcName)s]: %(message)s")
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
        },
    )


class Bot:
    """
    Main Bot class
    """

    def __init__(self) -> None:
        self.bot = DiscordBot()
        self.create_cogs()
        self.setup_events()

    def create_cogs(self):
        """
        Create Cogs
        """
        self.bot_admin = BotAdmin(self.bot)
        self.audio_player = AudioPlayer(self.bot)
        self.users_related = UsersRelated(self.bot)

    def setup_events(self):
        """
        Setup events
        """

        @self.bot.event
        async def on_ready():
            """
            Event that occurrence one time when bot is ready to work
            """
            logging.info('Logged in as %s (ID: %d)\n-----------\n', self.bot.user, self.bot.user.id)
            self.audio_player.init_cog()

        @self.bot.event
        async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
            """
            Event that occurrence whenever someone leaves/joins vc
            """
            await self.audio_player.disconnect_if_alone(member.guild.id)

    async def run(self):
        """
        Main boot start function
        """
        discord.utils.setup_logging(level=logging.WARNING, root=False)
        # Load cogs
        async with self.bot:
            await self.bot.add_cog(self.bot_admin)
            await self.bot.add_cog(self.users_related)
            await self.bot.add_cog(self.audio_player)
            await self.bot.start(os.getenv('BOT_TOKEN'))


bot = Bot()
try:
    asyncio.run(bot.run())
except KeyboardInterrupt:
    logging.info('Recieved interrupt signal.\nExiting...')
    sys.exit(1)
