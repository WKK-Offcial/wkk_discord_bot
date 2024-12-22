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
from cogs.badura_cog import BaduraCog
from discord_bot import DiscordBot

# Logger setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler("info.log"), logging.StreamHandler()],
)

# Load environment variables and dependencies
load_dotenv()
static_ffmpeg.add_paths()

# Load Opus library based on OS
if os.name == 'nt':
    discord.opus._load_default()
elif os.name == 'posix':
    discord.opus.load_opus('libopus.so.0')

if not discord.opus.is_loaded():
    raise RuntimeError('Failed to load Opus library.')


class Bot:
    """
    Main Bot class
    """

    def __init__(self) -> None:
        self.bot = DiscordBot()
        self._initialize_cogs()
        self._initialize_events()

    def _initialize_cogs(self):
        """
        Initialize and configure all bot cogs.
        """
        self.admin_cog = AdminCog(self.bot)
        self.audio_cog = AudioCog(self.bot)
        self.user_cog = UserCog(self.bot)
        self.badura_cog = BaduraCog(self.bot)

    def _initialize_events(self):
        """
        Configure bot events.
        """

        @self.bot.event
        async def on_ready():
            """
            Event triggered when the bot is ready.
            """
            logging.info("Logged in as %s (ID: %d)", self.bot.user, self.bot.user.id)
            logging.info("Bot is ready and operational.")

        @self.bot.event
        async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
            """
            Event triggered when a user's voice state changes.
            """
            player = member.guild.voice_client
            if player:
                await self.audio_cog.disconnect_player_if_alone_in_channel(player, 10)

    async def run(self):
        """
        Main function to start the bot.
        """
        discord.utils.setup_logging(level=logging.WARNING, root=False)

        async with self.bot:
            await self.bot.add_cog(self.admin_cog)
            await self.bot.add_cog(self.user_cog)
            await self.bot.add_cog(self.audio_cog)
            await self.bot.add_cog(self.badura_cog)
            await self.bot.start(os.getenv("BOT_TOKEN"))


def sigterm_handler(signum, frame):
    """
    Handler for SIGTERM signal.
    """
    logging.info("Received SIGTERM signal. Shutting down gracefully.")
    sys.exit(0)


def main():
    """
    Entry point of the script.
    """
    logging.info("Starting bot...")

    # Instantiate and run the bot
    bot = Bot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logging.info("Received interrupt signal. Exiting...")
        sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, sigterm_handler)
    main()
