import re

import discord
import wavelink

from utils.discord_bot import DiscordBot
from utils.endpoints import Endpoints


class WavelinkPlayer(wavelink.Player):
    """
    Wavelink player subclass
    """

    def __init__(self, client: DiscordBot, channel: discord.VoiceChannel) -> None:
        self.history = wavelink.Queue()
        super().__init__(client, channel)

    @property
    def is_connected(self) -> bool:
        """
        Check if the bot is is any voice channel
        """
        return bool(self.guild)

    async def connect(self, *, timeout: float, reconnect: bool, **kwargs) -> None:
        key_id, _ = self.channel._get_voice_client_key()
        state = self.channel._state
        if state._get_voice_client(key_id):
            return
        state._add_voice_client(key_id, self)
        ## basicaly original method of connecting but slightly changed so it supports our method of connecting
        if self.channel is None:
            raise RuntimeError('')

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
        # voice_client: discord.VoiceClient = discord.utils.get(self.client.voice_clients, guild=self.guild)
        # if not voice_client.is_connected():
        await self.connect(timeout=20, reconnect=True)
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
        if start is None:
            start = 0
        interrupted_time = getattr(track, 'interrupted_time', 0)
        if interrupted_time > start:
            start = interrupted_time
        await super().play(track=track, replace=replace, start=start, end=end, volume=volume, populate=populate)
        self._paused = False  # because it doesnt update if player is paused and we start playing something

    async def try_playing(self, tracks: list[wavelink.Playable], force_play: bool = False) -> None:
        """
        Tries to play the track.\n
        If currently playing then just add tracks to queue\n
        Passing force_play stops currently played song and puts it behind force played tracks
        """
        if force_play:
            tracks.reverse()  # we need to reverse list since we are using put_at_front later
        for track in tracks:
            if force_play:
                self.queue.put_at_front(track)
            else:
                await self.queue.put_wait(track)

        if not self.is_playing() or force_play:
            first_in_queue = self.queue.get()
            if self.is_playing() or self.is_paused():
                current_track = self.current
                setattr(current_track, 'interrupted_time', self.last_position)
                self.queue.put_at_index(len(tracks) - 1, current_track)
            # TODO: find other method of setting start_time and interrupted_time so that typehinting works
            await self.play(first_in_queue, start=getattr(first_in_queue, 'start_time', 0))

    async def search_tracks(self, search_phrase: str) -> list[wavelink.Playable]:
        """
        Decides which type of track should be used based on search phrase
        Args:
            search_phrase (str): text input from discord command user

        Returns:
            list[wavelink.Playable]: list of tracks in case of playlist, list with single track otherwise
        """
        start_time: int = 0
        youtube_playlist_regex = re.search(r"list=([^#\&\?]*).*", search_phrase)
        # Check if user wants to play audio from YouTube Playlist...
        try:
            if youtube_playlist_regex and youtube_playlist_regex.groups():
                safe_url = f'https://www.youtube.com/playlist?list={youtube_playlist_regex.groups()[0]}'
                playlist = await wavelink.YouTubePlaylist.search(safe_url, return_first=True)
                for track in playlist.tracks:
                    setattr(track, 'start_time', start_time)
                tracks = playlist.tracks
            # ...or soundboard...
            elif search_phrase.isdecimal():
                sound_id = int(search_phrase)
                guild_soundboard = Endpoints.get_soundboard(self.guild.id)
                if not guild_soundboard or sound_id > len(guild_soundboard):
                    tracks = None

                file_name = guild_soundboard[int(search_phrase) - 1]
                file_path = f'sounds/{str(self.guild.id)}/{file_name}'
                track = await wavelink.GenericTrack.search(file_path, return_first=True)
                setattr(track, 'start_time', start_time)
                tracks = [track]
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
                    track = await wavelink.YouTubeTrack.search(safe_url, return_first=True)
                    setattr(track, 'start_time', start_time)
                    tracks = [track]
                else:
                    track = await wavelink.YouTubeTrack.search(search_phrase, return_first=True)
                    setattr(track, 'start_time', start_time)
                    tracks = [track]
        except wavelink.NoTracksError:
            tracks = None
        if not tracks:
            raise NoTracksFound

        return tracks

    async def search_and_try_playing(self, search_query: str, force_play: bool = False) -> list[wavelink.Playable]:
        """
        Gets tracks from search_querry then tries to play them.\n
        Returns found tracks
        """
        tracks = await self.search_tracks(search_query)
        await self.try_playing(tracks, force_play=force_play)
        return tracks

    async def stop_all(self) -> None:
        """
        stops currenty playing track\n
        clears the queue
        """
        # Clear player
        self.queue.clear()
        await super().stop()

    async def next(self) -> None:
        """
        Skip to next song
        """
        if current := self.current:
            setattr(self.current, 'interrupted_time', self.last_position)

        if not self.queue.is_empty:
            next_track = await self.queue.get_wait()
            if current:
                await self.history.put_wait(self.current)
            await self.play(next_track, start=getattr(next_track, 'start_time', 0))
        elif self.is_playing():
            await super().stop()

    async def previous(self) -> None:
        """
        plays previous track
        """
        if self.history.is_empty:
            return
        track: wavelink.Playable = self.history.pop()
        if current := self.current:
            setattr(current, 'interrupted_time', self.last_position)
            self.queue.put_at_front(current)
        await self.play(track, start=getattr(track, 'start_time', 0))

    async def add_to_history(self, track: wavelink.Playable) -> None:
        """
        adds a track at the front of history queue
        """
        await self.history.put_wait(track)

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
