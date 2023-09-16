import asyncio
import re

import discord
import wavelink

from utils.discord_bot import DiscordBot
from utils.endpoints import Endpoints

from .wavelink_queue import WavelinkQueue


class WavelinkPlayer(wavelink.Player):
    """
    Wavelink player subclass
    """

    def __init__(self, client: DiscordBot, channel: discord.VoiceChannel) -> None:
        self.history: WavelinkQueue = WavelinkQueue()
        self.start_times: dict[int, int] = {}  # title: time
        self.interupt_times: dict[int, int] = {}  # title: time
        self._current_track: wavelink.Playable | None = None
        super().__init__(client, channel)
        self.queue: WavelinkQueue = WavelinkQueue()

    def __del__(self):
        coro = self.disconnect()
        asyncio.run_coroutine_threadsafe(coro, self.client.loop)

    @property
    def is_connected(self) -> bool:
        """
        Check if the bot is is any voice channel
        """
        return bool(self.guild)

    async def connect(self, *, timeout: float, reconnect: bool, **kwargs) -> None:
        voice_channel = kwargs.get("voice_channel", None)
        if voice_channel is None:
            raise RuntimeError('voice_channel not passed')
        del kwargs["voice_channel"]
        if self.channel is None:
            self.channel = voice_channel
        key_id, _ = self.channel._get_voice_client_key()
        state = self.channel._state
        if state._get_voice_client(key_id):
            return
        state._add_voice_client(key_id, self)
        ## basicaly original method of connecting but slightly changed so it supports our method of connecting

        if not self._guild:
            self._guild = self.channel.guild

        if not self.current_node._players.get(self._guild.id):
            self.current_node._players[self._guild.id] = self

        await self.channel.guild.change_voice_state(channel=self.channel, **kwargs)
        ## end of connect method
        await self.set_filter(wavelink.Filter())

    async def connect_and_move_to(self, voice_channel: discord.VoiceChannel):
        """
        Connect if not connected, then move to the voicechannel if not already in it
        """
        await self.connect(timeout=20, reconnect=True, voice_channel=voice_channel)
        if self.channel.id != voice_channel.id:
            await super().move_to(voice_channel)

    async def disconnect(self, **kwargs):
        await self.stop_all()
        await super().disconnect(**kwargs)

    async def play(
        self,
        track: wavelink.Playable,
        replace: bool = True,
        start: int | None = None,
        end: int | None = None,
        volume: int | None = None,
        *,
        populate: bool = False,
    ) -> wavelink.Playable:
        """
        Play a WaveLink Track.

        Parameters
        ----------
        track: :class:`tracks.Playable`
            The :class:`tracks.Playable` track to start playing.
        replace: bool
            Whether this track should replace the current track. Defaults to ``True``.
        start: Optional[int]
            The position to start the track at in milliseconds.
            Defaults to ``None`` which will start the track at the beginning.\n
            * Left to have same signature as original play however should not be used.\n
            * This play gets its start_times from start_times dict\n
        end: Optional[int]
            The position to end the track at in milliseconds.
            Defaults to ``None`` which means it will play until the end.
        volume: Optional[int]
            Sets the volume of the player. Must be between ``0`` and ``1000``.
            Defaults to ``None`` which will not change the volume.
        populate: bool
            Whether to populate the AutoPlay queue. This is done automatically when AutoPlay is on.
            Defaults to False.

        Returns
        -------
        :class:`tracks.Playable`
            The track that is now playing.
        """

        if start is not None:
            raise ValueError('You should not pass start_time here. Consider using try_playing')
        start = self.start_times.get(track.title, 0)
        interrupted_time = self.interupt_times.get(track.title, 0)
        if interrupted_time > start:
            start = interrupted_time
        returned_track = await super().play(
            track=track, replace=replace, start=start, end=end, volume=volume, populate=populate
        )
        self._paused = False  # because it doesnt update if player is paused and we start playing something
        self._current_track = track
        return returned_track

    async def track_finished(self):
        """
        Plays the next song in queue if it exists.
        Also adds the finished track to history
        If something is playing it raises exception.

        Since we are not using autoplay thats how we get voiceplayer to play another track.
        """
        if self.is_playing():
            raise ValueError('bot is playing right now')
        self.interupt_times.pop(self._current_track.title, None)
        await self.history.put_wait(self._current_track)
        if not self.queue.is_empty:
            first_in_queue = await self.queue.get_wait()
            await self.play(track=first_in_queue)
        else:
            self._current_track = None

    async def try_playing(
        self, tracks: list[wavelink.Playable], *, start_time: int = 0, force_play: bool | None = False
    ) -> None:
        """
        Adds tracks to queue\n
        If nothing is playing then plays the first track in queue\n
        \n
        When force_play is true adds track to the front of the queue then plays the first track no mather what\n
        if track was playing it is moved to the history queue
        """
        if force_play:
            tracks.reverse()  # we need to reverse list since we are using put_at_front later
        for track in tracks:
            self.start_times[track.title] = start_time
            if force_play:
                self.queue.put_at_front(track)
            else:
                await self.queue.put_wait(track)

        if not self.is_playing() or force_play:
            first_in_queue = self.queue.get()
            if self.is_playing() or self.is_paused():
                current_track = self.current
                self.interupt_times[current_track.title] = self.last_position
                self.queue.put_at_index(len(tracks) - 1, current_track)
            await self.play(first_in_queue)

    async def play_from_queue(self, index: int, *, history: bool = False, force_play: bool = True) -> None:
        """Plays the track from the queue from the given index and removes it from the queue

        Args:
            index (int): place in the queue
            history (bool, optional): Whether to get track from current queue or history queue. Defaults to False.
            force_play (bool, optional): Whether . Defaults to True.
        """
        track = self.history.pop_index(index) if history else self.queue.pop_index(index)
        await self.try_playing([track], start_time=self.start_times.get(track.title, 0), force_play=force_play)

    async def search_tracks(self, search_phrase: str) -> tuple[list[wavelink.Playable], int]:
        """
        Decides which type of track should be used based on search phrase
        Args:
            search_phrase (str): text input from discord command user

        Returns:
            tuple[list[wavelink.Playable], int]: tuple with list of tracks in case of playlist with start_time = 0,\n
            list with single track and start time otherwise.

        """
        start_time: int = 0
        youtube_playlist_regex = re.search(r"list=([^#\&\?]*).*", search_phrase)
        # Check if user wants to play audio from YouTube Playlist...
        try:
            if youtube_playlist_regex and youtube_playlist_regex.groups():
                safe_url = f'https://www.youtube.com/playlist?list={youtube_playlist_regex.groups()[0]}'
                playlist = await wavelink.YouTubePlaylist.search(safe_url)
                tracks = playlist.tracks
            # ...or soundboard...
            elif search_phrase.isdecimal():
                sound_id = int(search_phrase)
                guild_soundboard = Endpoints.get_soundboard(self.guild.id)
                if not guild_soundboard or sound_id > len(guild_soundboard):
                    tracks = None

                file_name = guild_soundboard[int(search_phrase) - 1]
                file_path = f'sounds/{str(self.guild.id)}/{file_name}'
                track = await wavelink.GenericTrack.search(file_path)
                tracks = [track[0]]
            # ...Else search_phrase on youtube.
            else:
                # Check if start time was passed
                start_time_regex = re.search(r"(?:[\?&])?t=([0-9]+)", search_phrase)
                if start_time_regex and start_time_regex.groups()[0]:
                    start_time = int(start_time_regex.groups()[0]) * 1000

                # We need to extract vid id because wavelink does not support shortened links
                video_id_regex = re.search(
                    r"youtu(?:be\.com\/watch\?v=|\.be\/)([\w\-\_]*)(&(amp;)?[\w\?=]*)?", search_phrase
                )
                if video_id_regex and video_id_regex.groups()[0]:
                    safe_url = f'https://www.youtube.com/watch?v={video_id_regex.groups()[0]}'
                    track = await wavelink.YouTubeTrack.search(safe_url)
                    tracks = [track[0]]
                else:
                    track = await wavelink.YouTubeTrack.search(search_phrase)
                    tracks = [track[0]]
        except wavelink.NoTracksError:
            tracks = None
        if not tracks:
            raise NoTracksFound

        return tracks, start_time

    async def search_and_try_playing(
        self, search_query: str, force_play: bool | None = False
    ) -> list[wavelink.Playable]:
        """
        Gets tracks from search_querry then tries to play them.\n
        Returns list of found tracks
        """
        tracks, start_time = await self.search_tracks(search_query)
        await self.try_playing(tracks, start_time=start_time, force_play=force_play)
        return tracks

    async def stop_all(self) -> None:
        """
        stops currenty playing track\n
        clears the queue
        """
        # Clear player
        self.queue.clear()
        await self.stop()

    async def stop(self) -> None:
        """
        stops the currently playing track and add it to history.
        Does nothing if nothing is playing.
        """

        if current := self.current:
            self.interupt_times[current.title] = self.last_position
            await self.history.put_wait(current)
        await super().stop()

    async def skip(self) -> None:
        """
        Skip to next song if nothing in the queue it stops current track
        """
        if current := self.current:
            self.interupt_times[current.title] = self.last_position
            await self.history.put_wait(current)
        if not self.queue.is_empty:
            next_track = await self.queue.get_wait()
            await self.play(next_track)
        elif self.is_playing():
            await super().stop()

    async def previous(self) -> None:
        """
        plays previous track if available.
        Does nothing if there is nothing in history
        """
        if self.history.is_empty:
            return
        track: wavelink.Playable = self.history.pop()
        if current := self.current:
            self.interupt_times[current.title] = self.last_position
            self.queue.put_at_front(current)
        await self.play(track)

    async def toggle_pause(self):
        """
        toggles pause on or off
        """
        if not self.is_paused():
            await self.pause()
        else:
            await self.resume()

    async def toggle_cursed_filter(self):
        """
        toggles the 4th density filter
        """
        if not self.filter:
            filter_ = wavelink.Filter(
                tremolo=wavelink.Tremolo(frequency=4, depth=0.3),
                vibrato=wavelink.Vibrato(frequency=14, depth=1),
                timescale=wavelink.Timescale(pitch=0.8),
            )
        else:
            filter_ = wavelink.Filter()
        await self.set_filter(filter_)


class WavelinkPlayerException(Exception):
    """
    Base Exception for all WavelinkPlayer exceptions
    """


class NoTracksFound(WavelinkPlayerException):
    """
    Exception for when WavelinkPlayer couldn't find a track
    """
