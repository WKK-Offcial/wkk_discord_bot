import wavelink
import discord
from discord.abc import Connectable
from discord.utils import MISSING


class AudioPlayer(wavelink.Player):
    """
    Extends the functionality of the default Wavelink player class.
    """

    def __init__(
        self,
        client: discord.Client = MISSING,
        channel: Connectable = MISSING,
        *,
        nodes: list[wavelink.Node] | None = None,
    ):
        super().__init__(client=client, channel=channel, nodes=nodes)
        self._filters_applied = False

    @property
    def filters_applied(self) -> bool:
        """
        Indicates whether audio filters are currently applied.
        """
        return self._filters_applied

    async def play_track(self, playable: wavelink.Search, start_time: int = 0) -> None:
        """
        Plays a track, starting at a specific time.

        Args:
            playable (wavelink.Search): The track to be played.
            start_time (int): The time (in seconds) to start playback. Defaults to 0.
        """
        self.autoplay = wavelink.AutoPlayMode.partial
        await self.queue.put_wait(playable)
        if not self.playing:
            await self.play(self.queue.get(), start=start_time)

    async def play_previous_track(self) -> None:
        """
        Plays the previously played track from the queue history.
        """
        queue = self.queue
        history = self.queue.history

        if self.playing:
            current_track = history[-1]
            previous_track = history[-2]
            queue._queue.appendleft(current_track)  # Moves the current track back to the queue
            await history.delete(-1)  # Removes the current track from history
        else:
            previous_track = history[-1]

        await self.play(previous_track, add_history=False)

    async def play_track_from_queue(self, index: int) -> None:
        """
        Plays a specific track from the queue by index.

        Args:
            index (int): The index of the track in the queue.
        """
        track = self.queue[index]
        await self.queue.delete(index)
        await self.play(track)

    async def play_track_from_history(self, index: int) -> None:
        """
        Plays a specific track from the queue history by index.

        Args:
            index (int): The index of the track in the history.
        """
        history = self.queue.history
        track = history[index]
        await history.delete(index)
        await self.play(track)

    async def disable_filters(self) -> None:
        """
        Disables all currently applied audio filters.
        """
        await self.set_filters()
        self._filters_applied = False

    async def toggle_nightcore_filter(self) -> None:
        """
        Toggles the Nightcore audio filter on or off.
        """
        if self._filters_applied:
            await self.set_filters()  # Resets filters to default
        else:
            filters = wavelink.Filters()
            filters.timescale.set(pitch=1.2, speed=1.1, rate=1.0)
            filters.equalizer.reset()
            await self.set_filters(filters)

        self._filters_applied = not self._filters_applied
