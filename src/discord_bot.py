import logging
import os
from types import TracebackType
from typing import Optional, Type

import wavelink
from discord import Intents
from discord.ext import commands


class DiscordBot(commands.Bot):
    """
    Extends the default bot class functionality.
    """

    def __init__(self) -> None:
        intents = Intents.default()
        intents.message_content = True  # Enables the bot to access message content.
        super().__init__(
            command_prefix=commands.when_mentioned_or("/"),
            description="The Boi is back",
            intents=intents,
        )

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """
        Clean up resources and run destructors for cogs, if defined.
        """
        for cog in self.cogs.values():
            if hasattr(cog, "__del__"):
                cog.__del__()  # Call explicitly to ensure cleanup.
        await super().__aexit__(exc_type, exc_value, traceback)

    async def setup_hook(self) -> None:
        """
        Connect to the Lavalink server during bot setup.
        """
        node_url = f"{os.getenv('WAVELINK_URL')}:{os.getenv('WAVELINK_PORT')}"
        node = wavelink.Node(uri=node_url, password=os.getenv('WAVELINK_PASSWORD'))

        try:
            await wavelink.Pool.connect(client=self, nodes=[node])
            logging.info("Connected to Lavalink server successfully.")
        except wavelink.exceptions.WavelinkException as err:
            logging.warning("Could not connect to the Lavalink server.")
            logging.warning(err)
