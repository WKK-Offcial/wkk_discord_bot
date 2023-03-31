import asyncio
import logging
import os

import discord
import sentry_sdk
import static_ffmpeg
from dotenv import load_dotenv

from cogs.audio_player import AudioPlayer
from cogs.bot_admin import BotAdmin
from cogs.users_related import UsersRelated
from utils.discord_bot import DiscordBot
from utils.misc import delay_coro

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
            self.audio_player.init_voice_client()

        @self.bot.event
        async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
            """
            Event that occurrence whenever someone leaves/joins vc
            """
            voice_state = member.guild.voice_client
            # Checking if the bot is connected to a channel
            # and if there is only 1 member connected to it (the bot itself)
            if voice_state is not None and len(voice_state.channel.members) == 1:
                await delay_coro(coro=self.audio_player.disconnect_when_alone(member.guild.id), seconds=60)

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
asyncio.run(bot.run())
