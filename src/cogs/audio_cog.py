from __future__ import annotations

import asyncio
from io import BytesIO
import re
from typing import cast

import discord
import wavelink
from discord import app_commands
from discord.ext import commands
from utils.decorators import user_is_in_voice_channel_check
from utils.endpoints import Endpoints
from views.audio_player_view import AudioPlayerView
from exceptions.wavelink_exceptions import YoutubeTrackNotFound, UnexpectedPlayableType
from exceptions.user_exceptions import SoundboardTrackNotFound
from exceptions.exception_handler import ExceptionHandler
from audio_player import AudioPlayer
from discord_bot import DiscordBot


class AudioCog(commands.Cog):
    """
    Cog for handling music commands and soundboard functionality.
    Manages a dictionary of audio control views for each guild.
    """

    def __init__(self, bot: DiscordBot) -> None:
        self.bot = bot
        self.views: dict[int, AudioPlayerView] = {}
        self.exception_handler = ExceptionHandler()

    def __del__(self):
        for view in self.views.values():
            if hasattr(view, '__del__'):
                view.__del__()

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="play")
    @user_is_in_voice_channel_check
    async def play(self, interaction: discord.Interaction, search: str) -> None:
        """
        Play audio from soundboard or YouTube. Supports search phrases or URLs.
        """
        await interaction.response.send_message(f"Searching for: {search}...")
        guild_id = interaction.guild_id
        user_channel = interaction.user.voice.channel

        player = cast(AudioPlayer, interaction.guild.voice_client)
        if not player or not player.connected:
            player = await user_channel.connect(cls=AudioPlayer, timeout=20)
        elif player.channel != user_channel:
            await player.move_to(user_channel)

        view = self.views.get(guild_id)
        if not view:
            view = AudioPlayerView(self.bot, interaction.channel)
            self.views[guild_id] = view

        try:
            result, start_time = await self.__search_tracks(search, guild_id)
            response = f"Found: \"{result.name if isinstance(result, wavelink.Playlist) else result.title}\"."
            await interaction.edit_original_response(content=response)
            await player.play_track(result, start_time)
            await view.send_embed()
        except Exception as err:
            message = self.exception_handler.handle(err)
            await interaction.edit_original_response(content=message)

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="skip")
    @user_is_in_voice_channel_check
    async def skip(self, interaction: discord.Interaction) -> None:
        """
        Skip the current track.
        """
        player = cast(AudioPlayer, interaction.guild.voice_client)
        await player.skip()

        if player.queue:
            await interaction.response.send_message(f"Skipped to: \"{player.current.title}\".")
        else:
            await interaction.response.send_message("Track skipped.")

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="disconnect")
    async def disconnect(self, interaction: discord.Interaction) -> None:
        """
        Disconnect the bot from the voice channel.
        """
        player = cast(AudioPlayer, interaction.guild.voice_client)
        if not player or not player.connected:
            await interaction.response.send_message(
                "Not connected to any voice channel.", ephemeral=True, delete_after=3
            )
            return

        await self.__remove_view_and_disconnect_player(player)
        await interaction.response.send_message("Bot disconnected.", ephemeral=True, delete_after=3)

    @commands.guild_only()
    @app_commands.command(name="soundboard")
    async def list_soundboard(self, interaction: discord.Interaction):
        """
        List all audio files uploaded to the soundboard.
        """
        await interaction.response.send_message("Preparing soundboard list...")
        soundboard = Endpoints.get_soundboard(interaction.guild_id)
        if not soundboard:
            await interaction.edit_original_response(content="No files uploaded!")
            return

        content = "SOUNDBOARD\n" + "\n".join(
            f"{i + 1}. {entry.replace('_', ' - ', 1).replace('_', ' ').capitalize().split('.mp3')[0]}"
            for i, entry in enumerate(soundboard)
        )

        file = discord.File(BytesIO(content.encode("utf-8")), filename="soundboard.txt")
        await interaction.edit_original_response(content="", attachments=[file])

    @commands.guild_only()
    @app_commands.command(name="volume")
    async def set_volume(self, interaction: discord.Interaction, value: int):
        """
        Set the bot's playback volume (0-100).
        """
        if not (0 <= value <= 100):
            await interaction.response.send_message(
                "Volume must be between 0 and 100.", ephemeral=True, delete_after=3
            )
            return

        player = cast(AudioPlayer, interaction.guild.voice_client)
        if player.connected:
            await player.set_volume(value)
            await interaction.response.send_message(f"Volume set to {value}.", delete_after=15)
        else:
            await interaction.response.send_message("Bot must be in a voice channel.", ephemeral=True, delete_after=3)

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="upload")
    async def upload_audio(self, interaction: discord.Interaction, mp3_file: discord.Attachment):
        """
        Upload an audio file to the soundboard.
        """
        await interaction.response.send_message("Processing file...")

        if not mp3_file.filename.endswith(".mp3"):
            await interaction.edit_original_response(content="Only .mp3 files are allowed.")
            return

        file_bytes = await mp3_file.read()
        result = Endpoints.upload_audio(interaction.guild_id, mp3_file.filename, file_bytes)
        await interaction.edit_original_response(content=result)

    async def __search_tracks(self, search: str, guild_id: int) -> tuple[wavelink.Playable | wavelink.Playlist, int]:
        """
        Search for tracks on YouTube or the soundboard.
        """
        start_time = 0
        youtube_playlist_regex = re.search(r"list=([^#&?]*)", search)

        if youtube_playlist_regex:
            playlist_id = youtube_playlist_regex.group(1)
            result = await wavelink.Playable.search(f"https://www.youtube.com/playlist?list={playlist_id}")
            if isinstance(result, wavelink.Playlist):
                return result, start_time
            raise UnexpectedPlayableType

        if search.isdigit():
            soundboard = Endpoints.get_soundboard(guild_id)
            if soundboard and int(search) <= len(soundboard):
                file_name = soundboard[int(search) - 1]
                result = await wavelink.Pool.fetch_tracks(f"sounds/{guild_id}/{file_name}")
                return result[0], start_time
            raise SoundboardTrackNotFound

        video_id_regex = re.search(r"(?:youtu\.be/|youtube\.com/watch\?v=)([\w-]+)", search)
        if video_id_regex:
            video_id = video_id_regex.group(1)
            result = await wavelink.Playable.search(f"https://www.youtube.com/watch?v={video_id}")
        else:
            result = await wavelink.Playable.search(search)

        if not result:
            raise YoutubeTrackNotFound

        start_time_regex = re.search(r"(?:[?&])t=(\d+)", search)
        if start_time_regex:
            start_time = int(start_time_regex.group(1)) * 1000

        return result[0], start_time

    async def disconnect_player_if_alone_in_channel(self, player: AudioPlayer, delay: int = 2):
        """
        Disconnect the player if it's alone in the voice channel after a delay.
        """
        await asyncio.sleep(delay)
        if player.channel and len(player.channel.members) == 1:
            await self.__remove_view_and_disconnect_player(player)

    async def __remove_view_and_disconnect_player(self, player: AudioPlayer):
        """
        Remove the view associated with the guild and disconnect the player.
        """
        guild_id = player.guild.id
        if guild_id in self.views:
            self.views[guild_id].remove_view()
            del self.views[guild_id]
        await player.disconnect()

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        """
        Triggered when a track finishes playing.
        """
        player = cast(AudioPlayer, payload.player)
        view = self.views.get(player.guild.id)
        await asyncio.sleep(0.1)
        if not player.queue and not player.playing:
            await player.disable_filters()
        await view.send_embed()
