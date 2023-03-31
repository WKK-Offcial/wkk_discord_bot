import re

import discord
import wavelink
from wavelink import Playable, Player, Queue

from utils.discord_bot import DiscordBot
from utils.endpoints import Endpoints


class WavelinkPlayer(Player):
    """
    Wavelink player subclass
    """

    def __init__(self, client: DiscordBot, channel: discord.VoiceChannel) -> None:
        super().__init__(client, channel)
        self.history = Queue()
        self.track_start_times: dict[str, int] = {}

    async def connect(self, *, timeout: float, reconnect: bool, **kwargs) -> None:
        key_id, _ = self.channel._get_voice_client_key()
        state = self.channel._state
        state._add_voice_client(key_id, self)
        await super().connect(timeout=timeout, reconnect=reconnect, **kwargs)
        await self.set_filter(wavelink.Filter())

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

    async def connect_and_move_to(self, voice_channel: discord.VoiceChannel):
        """
        Connect if not connected, then move to the voicechannel if not already in it
        """
        # voice_client: discord.VoiceClient = discord.utils.get(self.client.voice_clients, guild=self.guild)
        # if not voice_client.is_connected():
        await self.connect(timeout=20, reconnect=True)
        if self.channel.id != voice_channel.id:
            await super().move_to(voice_channel)

    async def search_and_play(self, search_query: str, force_play: bool = False) -> list[wavelink.Playable]:
        """
        Gets tracks from search_querry then tries to play them.\n
        Returns found tracks
        """
        tracks = await self.search_tracks(search_query)
        await self.try_playing(tracks, force_play=force_play)
        return tracks

    async def try_playing(self, tracks: list[wavelink.Playable], force_play: bool = False) -> None:
        """
        Tries to play the track.\n
        If currently playing then just add tracks to queue\n
        Passing force_play stops currently played song and puts it behind force played tracks
        """
        # TODO respect start times

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
                self.queue.put_at_index(len(tracks) - 1, current_track)

            await self.play(first_in_queue)

    async def search_tracks(self, search_querry: str) -> list[wavelink.Playable]:
        """
        searches for a song based on a given querry,
        returns a list of tuples with track and start_times
        """
        guild_id = self.guild.id
        # TODO add start time to tracks
        start_time: int = 0
        # Check if user wants to play audio from YouTube Playlist...
        try:
            youtube_playlist_regex = re.search(r"list=([^#\&\?]*).*", search_querry)
            if youtube_playlist_regex and youtube_playlist_regex.groups():
                safe_url = f'https://www.youtube.com/playlist?list={youtube_playlist_regex.groups()[0]}'
                playlist = await wavelink.YouTubePlaylist.search(safe_url, return_first=True)
                audio_tracks = [track for track in playlist.tracks]
            # ...or soundboard...
            elif search_querry.isdecimal():
                sound_id = int(search_querry)
                guild_soundboard = Endpoints.get_soundboard(guild_id)
                if not guild_soundboard or sound_id > len(guild_soundboard):
                    raise NoTracksFound

                file_name = guild_soundboard[int(search_querry) - 1]
                file_path = f'sounds/{str(guild_id)}/{file_name}'
                audio_tracks = [await wavelink.GenericTrack.search(file_path, return_first=True)]
            # ...Else search on youtube.
            else:
                # Check if start time was passed
                start_time_regex = re.search(r"(?:[\?&])?t=([0-9]+)", search_querry)
                if start_time_regex and start_time_regex.groups()[0]:
                    start_time = int(start_time_regex.groups()[0]) * 1000

                # We need to extract vid id because wavelink does not support shortened links
                video_id_regex = re.search(
                    r"youtu(?:be\.com\/watch\?v=|\.be\/)([\w\-\_]*)(&(amp;)?[\w\?=]*)?", search_querry
                )
                if video_id_regex and video_id_regex.groups()[0]:
                    safe_url = f'https://www.youtube.com/watch?v={video_id_regex.groups()[0]}'
                    audio_tracks = [await wavelink.YouTubeTrack.search(safe_url, return_first=True)]
                else:
                    audio_tracks = [await wavelink.YouTubeTrack.search(search_querry, return_first=True)]

            return audio_tracks
        except wavelink.exceptions.NoTracksError as exc:
            raise NoTracksFound from exc


class WavelinkPlayerException(Exception):
    """
    Base Exception for all WavelinkPlayer exceptions
    """


class NoTracksFound(WavelinkPlayerException):
    """
    Exception for when WavelinkPlayer couldn't find a track
    """
