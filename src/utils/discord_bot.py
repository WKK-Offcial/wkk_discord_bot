import logging
import os
from types import TracebackType
from typing import Optional, Type

import wavelink
from discord import Intents
from discord.ext import commands


class DiscordBot(commands.Bot):
    """
    Expands default bot class functionality
    """

    def __init__(self):
        intents = Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or("/"),
            description='The Boi is back',
            intents=intents,
        )

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        # run cogs destructors if defined
        for cog in self.cogs.values():
            if hasattr(cog, '__del__'):
                cog.__del__()  # since just using del doesnt guarantee that destructor runs in async resource
        return await super().__aexit__(exc_type, exc_value, traceback)

    async def setup_hook(self) -> None:
        """
        Connect to lavalink server
        """
        node_url = f"{os.getenv('WAVELINK_URL')}:{os.getenv('WAVELINK_PORT')}"
        node: wavelink.Node = wavelink.Node(uri=node_url, password=os.getenv('WAVELINK_PASSWORD'))
        try:
            await wavelink.NodePool.connect(client=self, nodes=[node])
        except wavelink.exceptions.WavelinkException as err:
            logging.warning("Could not connect to lavalink!")
            logging.warning(err)
