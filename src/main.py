import asyncio
import logging
import os
import signal
import sys

import discord
import static_ffmpeg
from dotenv import load_dotenv

from cogs.audio_cog import AudioCog
from cogs.admin_cog import AdminCog
from cogs.user_cog import UserCog
from discord_bot import DiscordBot

# Set up logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler("info.log"), logging.StreamHandler()],
)
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
        self.bot_admin = AdminCog(self.bot)
        self.audio = AudioCog(self.bot)
        self.users_related = UserCog(self.bot)

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

        @self.bot.event
        async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
            """
            Event that occurrence whenever someone leaves/joins vc
            """
            player = member.guild.voice_client
            if player:
                await self.audio.disconnect_player_if_alone_in_channel(player, 10)

    async def run(self):
        """
        Main boot start function
        """
        discord.utils.setup_logging(level=logging.WARNING, root=False)
        # Load cogs
        async with self.bot:
            await self.bot.add_cog(self.bot_admin)
            await self.bot.add_cog(self.users_related)
            await self.bot.add_cog(self.audio)
            await self.bot.start(os.getenv('BOT_TOKEN'))


def sigterm_handler(signum, frame):
    """
    Handler for SIGTERM signal
    """
    logging.info('Recieved SIGTERM signal.\nExiting...')
    sys.exit(1)


def main():
    """
    Main function
    """
    logging.info('Info log...')
    logging.warning('Warning log..')
    logging.error('error log..')

    bot = Bot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logging.info('Recieved interrupt signal.\nExiting...')
        sys.exit(1)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, sigterm_handler)
    main()
