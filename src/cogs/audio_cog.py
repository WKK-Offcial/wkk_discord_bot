from __future__ import annotations

import asyncio
import logging
from io import BytesIO
import re
from typing import TYPE_CHECKING, cast

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from utils.decorators import user_is_in_voice_channel_check
from utils.endpoints import Endpoints
from views.audio_player_view import AudioPlayerView
from exceptions.wavelink_exceptions import YoutubeTrackNotFound, UnexpectedPlayableType
from exceptions.user_exceptions import SoundboardTrackNotFound

if TYPE_CHECKING:
    from main import DiscordBot


class AudioCog(commands.Cog):
    """
    Class for music commands.
    self.views is dictionary that holds handle to a message with audio controls view {guild_id:view},
    """

    def __init__(self, bot: DiscordBot) -> None:
        self.bot: DiscordBot = bot
        self.views: dict[int, AudioPlayerView] = {}

    def __del__(self):
        for view in self.views.values():
            if hasattr(view, '__del__'):
                view.__del__()


    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="play")
    @user_is_in_voice_channel_check
    async def play(self, interaction: discord.Interaction, search: str, force_play: bool | None) -> None:
        """
        To use soundboard type audio ID from list. To use YouTube type url or a search phrase.
        """
        await interaction.response.send_message(f"Looking for {search}...")
        guild_id = interaction.guild_id
        user_channel = interaction.user.voice.channel


        # Connect to vc or change vc to the one caller is in
        player = cast(wavelink.Player, interaction.guild.voice_client)
        if not player or not player.connected:
            player = await user_channel.connect(cls=wavelink.Player, timeout=20)
        elif player.channel != user_channel:
            await player.move_to(user_channel)

        view = self.views.get(guild_id, None)
        if not view:
            view = AudioPlayerView(self.bot, interaction.channel)
            self.views[guild_id] = view

        player.autoplay = wavelink.AutoPlayMode.partial
        try:
            result, start_time = await self.__search_tracks(search, guild_id)
            if isinstance(result, wavelink.Playlist):
                await interaction.edit_original_response(content=f"Found \"{result.name}\".")
            else:
                await interaction.edit_original_response(content=f"Found \"{result.title}\".")

            await player.queue.put_wait(result)
            if not player.playing:
                await player.play(player.queue.get(), start=start_time)
            await view.send_embed()

        # Catch errors
        except YoutubeTrackNotFound as err:
            await interaction.edit_original_response(content="Youtube track not found!")
            logging.error(err)
        except SoundboardTrackNotFound as err:
            await interaction.edit_original_response(content="Soundboard track not found!")
            logging.error(err)
        except UnexpectedPlayableType as err:
            await interaction.edit_original_response(content="Server returned unexpected type!")
            logging.error(err)
        except SyntaxError as err:
            await interaction.edit_original_response(content='No argument passed!')
            logging.error(err.msg)
        except IndexError as err:
            await interaction.edit_original_response(content='No such number in soundboard')
            logging.error(err)
        except TypeError as err:
            await interaction.edit_original_response(content="Type error!")
            logging.error(err)

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="skip")
    @user_is_in_voice_channel_check
    async def skip(self, interaction: discord.Interaction) -> None:
        """
        To use soundboard type audio ID from list. To use YouTube type url or a search phrase.
        """
        player = cast(wavelink.Player, interaction.guild.voice_client)
        await player.skip()

        if player.queue:
            await interaction.response.send_message(f"Skipped track to \"{player.current.title}\".")
        else:
            await interaction.response.send_message("Skipped track.")

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="disconnect")
    async def disconnect(self, interaction: discord.Interaction) -> None:
        """
        Simple disconnect command.
        """
        player = cast(wavelink.Player, interaction.guild.voice_client)
        if not player.connected:
            await interaction.response.send_message(content='Bot is not connected to any voice channel',
                                                    ephemeral=True,
                                                    delete_after=3)
            return
        await self.__remove_view_and_disconnect(player)

        await interaction.response.send_message(content='Bot disconnected', ephemeral=True, delete_after=3)

    @commands.guild_only()
    @app_commands.command(name="soundboard")
    async def list_soundboard(self, interaction: discord.Interaction):
        """
        Lists all audio files uploaded to soundboard
        """
        await interaction.response.send_message("Preparing list...")
        guild_soundboard = Endpoints.get_soundboard(interaction.guild_id)
        if not guild_soundboard:
            await interaction.edit_original_response(content='No files uploaded!')
            return

        message_content = "SOUNDBOARD\n"
        i = 0
        for entry in guild_soundboard:
            i += 1
            message_content += f"{i}. {entry.replace('_', ' - ', 1).replace('_', ' ').capitalize().split('.mp3')[0]}\n"

        file = discord.File(fp=BytesIO(message_content.encode("utf8")), filename="soundboard.cpp")
        await interaction.edit_original_response(content='', attachments=[file])

    @commands.guild_only()
    @app_commands.command(name="volume")
    async def set_volume(self, interaction: discord.Interaction, value: int):
        """
        Set volume. Range: 0-100
        """
        if value < 0 or value > 100:
            await interaction.response.send_message("Value must be between 0 and 100", ephemeral=True, delete_after=3)
            return

        player = cast(wavelink.Player, interaction.guild.voice_client)
        if player.connected:
            await player.set_volume(value)
            await interaction.response.send_message(f"Value set to {value}", delete_after=15)
        else:
            await interaction.response.send_message("Bot must be in voice channel", ephemeral=True, delete_after=3)

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="upload")
    async def upload_audio(self, interaction: discord.Interaction, mp3_file: discord.Attachment):
        """
        Upload audio file to soundboard
        """
        await interaction.response.send_message("Processing file...")

        if not mp3_file.filename.endswith(".mp3"):
            await interaction.edit_original_response(content='Audio files must have .mp3 format')
            return

        mp3_file_bytes = await mp3_file.read()
        result = Endpoints.upload_audio(interaction.guild_id, mp3_file.filename, mp3_file_bytes)
        await interaction.edit_original_response(content=result)

    async def __search_tracks(self, search_phrase: str, guild_id: str) \
        -> tuple[wavelink.Playable | wavelink.Playlist, int]:
        """
        Decides which type of track should be used based on search phrase
        Args:
            search_phrase (str): text input from discord command user

        Returns:
            tuple[list[wavelink.Playable], int]: tuple with list of tracks in case of playlist with start_time = 0,\n
            list with single track and start time otherwise.

        """
        start_time: int = 0
        tracks = None
        youtube_playlist_regex = re.search(r"list=([^#\&\?]*).*", search_phrase)

        # Check if it's a YouTube playlist...
        if youtube_playlist_regex and youtube_playlist_regex.groups():
            # Build safe url to avoid errors
            safe_url = f'https://www.youtube.com/playlist?list={youtube_playlist_regex.groups()[0]}'
            search_result = await wavelink.Playable.search(safe_url)
            if isinstance(search_result, wavelink.Playlist):
                tracks = search_result
                return tracks, start_time
            raise UnexpectedPlayableType

        # ...or track in the soundboard...
        if search_phrase.isdecimal():
            sound_id = int(search_phrase)
            guild_soundboard = Endpoints.get_soundboard(guild_id)
            if guild_soundboard and sound_id <= len(guild_soundboard):
                file_name = guild_soundboard[sound_id - 1]
                file_path = f'sounds/{guild_id}/{file_name}'
                search_result = await wavelink.Pool.fetch_tracks(file_path)
                tracks = search_result[0]
                return tracks, start_time
            raise SoundboardTrackNotFound

        # ...otherwise search given phrase on youtube
        # Check if start time was passed
        start_time_regex = re.search(r"(?:[\?&])?t=([0-9]+)", search_phrase)
        if start_time_regex and start_time_regex.groups()[0]:
            start_time = int(start_time_regex.groups()[0]) * 1000

        # Build safe url to avoid errors
        video_id_regex = re.search(
            r"youtu(?:be\.com\/watch\?[^\s]*v=|\.be\/)([\w\-\_]*)(&(amp;)?[\w\?=]*)?", search_phrase
        )
        if video_id_regex and video_id_regex.groups()[0]:
            safe_url = f'https://www.youtube.com/watch?v={video_id_regex.groups()[0]}'
            search_result = await wavelink.Playable.search(safe_url)
        else:
            search_result = await wavelink.Playable.search(search_phrase)

        tracks = search_result[0]
        if not tracks:
            raise YoutubeTrackNotFound

        return tracks, start_time

    async def disconnect_if_alone(self, player: discord.VoiceProtocol, delay: int = 2):
        """
        removes a view from given guild and disconnects
        """
        await asyncio.sleep(delay)
        player: wavelink.Player = cast(wavelink.Player, player)
        if player.channel and player.connected and len(player.channel.members) == 1:
            await self.__remove_view_and_disconnect(player)

    async def __remove_view_and_disconnect(self, player: wavelink.Player):
        guild_id = player.guild.id
        await player.disconnect()
        if view := self.views.get(guild_id):
            view.remove_view()
            self.views.pop(guild_id)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        """
        Callback used when player finished playing a track
        Used only to update embed when all tracks finished playing since we'd use
        on_wavelink_track_start otherwise
        """
        player = payload.player
        view = self.views.get(player.guild.id)
        # Due to relying on validation from Lavalink player.playing property may in some cases
        # return True directly after skipping/stopping a track, so we wait a bit
        await asyncio.sleep(0.1)
        await view.send_embed()
