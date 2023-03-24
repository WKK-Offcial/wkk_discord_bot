from __future__ import annotations
import logging
import re
from io import BytesIO
from typing import TYPE_CHECKING

import discord
import wavelink
from discord import app_commands
from discord.ext import commands
from utils.endpoints import Endpoints
from views.audio_player_view import PlayerState

if TYPE_CHECKING:
    from main import DiscordBot

class AudioPlayer(commands.Cog):
    """
    Class for music commands.
    self.states is dictionary that holds handle to a player context (in particular, controllable player view)
    {guild_id:state}
    """

    def __init__(self, bot: DiscordBot) -> None:
        self.bot: DiscordBot = bot
        self.states: dict[int, PlayerState] = {}

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="play")
    async def play(self, interaction: discord.Interaction, search: str):
        """
        For soundboard type audio ID from list
        For YouTube type url or search phrase
        """
        await interaction.response.send_message(f"Looking for {search}...")

        guild_id = interaction.guild_id
        if interaction.user.voice:
            voice_channel = interaction.user.voice.channel
        else:
            await interaction.edit_original_response(content="You're not in a voice channel.")
            return

        # Connect to vc or change vc to the one caller is in
        bot_vc: wavelink.Player = interaction.guild.voice_client
        if not bot_vc:
            bot_vc = await voice_channel.connect(cls=wavelink.Player)
            await bot_vc.set_filter(wavelink.Filter())
        elif bot_vc.channel != voice_channel:
            await bot_vc.move_to(voice_channel)

        try:
            search_result, start_time = await self._add_to_queue(search, bot_vc)
            if not search_result:
                await interaction.edit_original_response(content=f"Couldn't find \"{search}\".")
                return

            await interaction.edit_original_response(content=f"Found \"{search_result.title}\".")
            if not bot_vc.is_playing():
                first_in_queue = await bot_vc.queue.get_wait()
                await bot_vc.play(first_in_queue, start=start_time)

            # Get/create view with audio controls
            if self.states.get(guild_id) is None:
                self.states[guild_id] = PlayerState(bot_vc, guild_id, self.bot, lambda: self._clear_state(guild_id))

            await self.states[guild_id].create_control_view_if_does_not_exist(interaction.channel)

        # Catch errors
        except SyntaxError as err:
            await interaction.edit_original_response(content='No argument passed!')
            logging.error(err.msg)
        except IndexError as err:
            await interaction.edit_original_response(content='Index out of range!')
            logging.error(err)
        except TypeError as err:
            await interaction.edit_original_response(content="Type error!")
            logging.error(err)

    def _clear_state(self, guild_id: int) -> None:
        self.states.pop(guild_id, None)

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name='disconnect')
    async def disconnect(self, interaction: discord.Interaction) -> None:
        """
        Simple disconnect command.
        This command assumes there is a currently connected Player.
        """
        bot_vc: wavelink.Player = interaction.guild.voice_client
        await bot_vc.disconnect()
        await interaction.response.send_message(content='Bot disconnected.', ephemeral=True, delete_after=3)

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

        bot_vc: wavelink.Player = interaction.guild.voice_client
        if bot_vc:
            await bot_vc.set_volume(value)
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
            await interaction.edit_original_response(content='Audio files must have mp3 format.')
            return

        mp3_file_bytes = await mp3_file.read()
        result = Endpoints.upload_audio(interaction.guild_id, mp3_file.filename, mp3_file_bytes)
        await interaction.edit_original_response(content=result)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEventPayload) -> None:
        """
        Callback function used for players to play next audio source in queue
        """
        guild_id = payload.player.guild.id
        bot_vc = payload.player
        state = self.states.get(guild_id)
        guild_queue = bot_vc.queue
        if guild_queue.count > 0:
            # Play next in queue
            next_audio_track = await guild_queue.get_wait()
            await bot_vc.play(next_audio_track)
            # Update embed
            await state.resend_control_view()
        elif state:
            await state.transit_to_queue_ended()
            await bot_vc.set_filter(wavelink.Filter())

    async def _add_to_queue(self, search: str, bot_vc: wavelink.Player) -> tuple[wavelink.Playable | None, int]:
        """
        Creates audio tracks and adds it to queue
        Returns first audio track and start time
        """
        guild_id = bot_vc.guild.id
        start_time = 0
        # Check if user wants to play audio from YouTube Playlist...
        try:
            youtube_playlist_regex = re.search(r"list=([^#\&\?]*).*", search)
            if youtube_playlist_regex and youtube_playlist_regex.groups():
                safe_url = f'https://www.youtube.com/playlist?list={youtube_playlist_regex.groups()[0]}'
                playlist = await wavelink.YouTubePlaylist.search(safe_url, return_first=True)
                for track in playlist.tracks:
                    await bot_vc.queue.put_wait(track)
                audio_track = playlist.tracks[0]
            # ...or soundboard...
            elif search.isdecimal():
                sound_id = int(search)
                guild_soundboard = Endpoints.get_soundboard(guild_id)
                if not guild_soundboard or sound_id > len(guild_soundboard):
                    return None

                file_name = guild_soundboard[int(search) - 1]
                file_path = f'sounds/{str(guild_id)}/{file_name}'
                audio_track = await wavelink.GenericTrack.search(file_path, return_first=True)
                await bot_vc.queue.put_wait(audio_track)
            # ...Else search on youtube.
            else:
                # Check if start time was passed
                start_time_regex = re.search(r"(?:[\?&])?t=([0-9]+)", search)
                if start_time_regex and start_time_regex.groups()[0]:
                    start_time = int(start_time_regex.groups()[0]) * 1000
                # We need to extract vid id because wavelink does not support shortened links
                video_id_regex = re.search(r"youtu(?:be\.com\/watch\?v=|\.be\/)([\w\-\_]*)(&(amp;)?[\w\?=]*)?", search)
                if video_id_regex and video_id_regex.groups()[0]:
                    safe_url = f'https://www.youtube.com/watch?v={video_id_regex.groups()[0]}'
                    audio_track = await wavelink.YouTubeTrack.search(safe_url, return_first=True)
                else:
                    audio_track = await wavelink.YouTubeTrack.search(search, return_first=True)
                await bot_vc.queue.put_wait(audio_track)
            return audio_track, start_time
        except wavelink.exceptions.NoTracksError:
            return None
        except wavelink.exceptions.WavelinkException:
            return None
