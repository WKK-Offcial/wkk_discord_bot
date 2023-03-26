from discord import VoiceChannel
from wavelink import Queue, Player
from utils.discord_bot import DiscordBot

class WavelinkPlayer(Player):
    """
    Wavelink player subclass
    """
    def __init__(self, client: DiscordBot , channel: VoiceChannel) -> None:
        super().__init__(client, channel)
        self.history = Queue()
        self.track_start_times: dict[str, int] = {}

