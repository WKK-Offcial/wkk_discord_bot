import logging
import os

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

    async def setup_hook(self):
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
