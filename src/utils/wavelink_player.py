from discord import VoiceChannel
from wavelink import Player, Queue

from utils.discord_bot import DiscordBot


class WavelinkPlayer(Player):
    """
    Wavelink player subclass
    """

    def __init__(self, client: DiscordBot, channel: VoiceChannel) -> None:
        super().__init__(client, channel)
        self.history = Queue()
        self.track_start_times: dict[str, int] = {}

    async def stop(self):
        """
        stops currenty playing track\n
        clears the queue
        """
        # Add to history
        current_track = self.current
        current_time = self.position
        self.track_start_times[current_track.title] = int(current_time)
        # Clear player
        self.queue.clear()
        await super().stop()
