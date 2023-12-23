import wavelink
import discord
from discord.abc import Connectable
from discord.utils import MISSING


class AudioPlayer(wavelink.Player):
    """
    Expands default wavelink player class functionality
    """
    def __init__(
        self, client: discord.Client = MISSING, channel: Connectable = MISSING, *, nodes: list[wavelink.Node] | None = None
        ):
        super().__init__(client=client, channel=channel, nodes=nodes)
        self._filters_applied = False

    @property
    def filters_applied(self):
        return self._filters_applied

    async def play_track(self, playable: wavelink.Search, start_time: int):
        self.autoplay = wavelink.AutoPlayMode.partial
        await self.queue.put_wait(playable)
        if not self.playing:
            await self.play(self.queue.get(), start=start_time)

    async def play_previous_track(self):
        queue = self.queue
        history = self.queue.history

        # If player is currently playing a track then last object in history is that track
        # (because button is disabled for the very first track)
        # otherwise last object in history is a previous track
        if self.playing:
            current_track = history[-1]
            previous_track = history[-2]
            queue._queue.appendleft(current_track)
            await history.delete(-1)
        else:
            previous_track = history[-1]

        await self.play(previous_track, add_history=False)

    async def play_track_from_queue(self, index: int):
        track = self.queue[index]
        await self.queue.delete(index)
        await self.play(track)

    async def play_track_from_history(self, index: int):
        history = self.queue.history
        track = history[index]
        await history.delete(index)
        await self.play(track)

    async def disable_filters(self):
        await self.set_filters()
        self._filters_applied = False

    async def toggle_nightcore_filter(self):
        if self._filters_applied:
            await self.set_filters()
        else:
            filters: wavelink.Filters = wavelink.Filters()
            filters.timescale.set(pitch=1.2, speed=1.1, rate=1)
            filters.equalizer.reset()
            await self.set_filters(filters)

        self._filters_applied = not self._filters_applied
