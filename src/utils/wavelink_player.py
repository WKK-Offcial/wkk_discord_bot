from discord import VoiceChannel
from wavelink import Playable, Player, Queue

from utils.discord_bot import DiscordBot


class WavelinkPlayer(Player):
    """
    Wavelink player subclass
    """

    def __init__(self, client: DiscordBot, channel: VoiceChannel) -> None:
        super().__init__(client, channel)
        self.history = Queue()
        self.track_start_times: dict[str, int] = {}

    async def stop_all(self) -> None:
        """
        stops currenty playing track\n
        clears the queue
        """
        # Add to history
        current_track: Playable = self.current
        current_time = self.position
        self.track_start_times[current_track.title] = int(current_time)
        # Clear player
        self.queue.clear()
        await super().stop()

    async def skip(self) -> None:
        """
        Skip to next song
        """
        # Add to history
        current_track: Playable = self.current
        current_time = self.position
        self.track_start_times[current_track.title] = int(current_time)
        if not current_track:
            raise ValueError('Nothing to skip')

        # Skip song
        await super().stop()
