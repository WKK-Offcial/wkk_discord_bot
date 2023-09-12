from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from typing import TYPE_CHECKING

import discord
import wavelink
from discord import app_commands
from discord.ext import commands
from wavelink import InvalidLavalinkResponse

from utils.decorators import user_is_in_voice_channel_check
from utils.endpoints import Endpoints

from .player_control_view import PlayerControlView
from .wavelink_player import NoTracksFound, WavelinkPlayer

if TYPE_CHECKING:
    from main import DiscordBot


class AudioCog(commands.Cog):
    """
    Class for music commands.
    self.views is dictionary that holds handle to a message with audio controls view {guild_id:view},
    """

    def __init__(self, bot: DiscordBot) -> None:
        self.bot: DiscordBot = bot
        self.voice_clients: dict[int, WavelinkPlayer] = {}
        self.views: dict[int, PlayerControlView] = {}
        self.track_state_change: dict[int, asyncio.Event] = {}

    def __del__(self):
        for voice_client in self.voice_clients.values():
            if hasattr(voice_client, '__del__'):
                voice_client.__del__()
        for view in self.views.values():
            if hasattr(view, '__del__'):
                view.__del__()

    def init_cog(self):
        """
        pupulate voice_client dictionary.\n
        Run this method after discord bot finished setting up
        """
        for guild in self.bot.guilds:
            self.voice_clients[guild.id] = WavelinkPlayer(self.bot, guild.voice_channels[0])
            self.track_state_change[guild.id] = asyncio.Event()

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="play")
    @user_is_in_voice_channel_check
    async def play(self, interaction: discord.Interaction, search: str, force_play: bool | None) -> None:
        """
        For soundboard type audio ID from list. For YouTube type url or search phrase.
        """
        await interaction.response.send_message(f"Looking for {search}...")
        guild_id = interaction.guild_id
        voice_channel = interaction.user.voice.channel

        # Connect to vc or change vc to the one caller is in
        voice_player: WavelinkPlayer = self.voice_clients[guild_id]
        await voice_player.connect_and_move_to(voice_channel)
        try:
            tracks = await voice_player.search_and_try_playing(search, force_play=force_play)
            await interaction.edit_original_response(content=f"Found \"{tracks[0].title}\".")
            view = self.get_view(interaction)
            await view.replace_message(voice_player)

        # Catch errors
        except NoTracksFound:
            await interaction.edit_original_response(content=f"Couldn't find \"{search}\".")
        except SyntaxError as err:
            await interaction.edit_original_response(content='No argument passed!')
            logging.error(err.msg)
        except IndexError as err:
            await interaction.edit_original_response(content='No such number in soundboard')
            logging.error(err)
        except TypeError as err:
            await interaction.edit_original_response(content="Type error!")
            logging.error(err)
        except InvalidLavalinkResponse as err:
            await interaction.edit_original_response(content="InvalidLavalinkResponse!")
            logging.error(err)

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name='disconnect')
    async def disconnect(self, interaction: discord.Interaction) -> None:
        """
        Simple disconnect command.
        """
        voice_client: WavelinkPlayer = self.voice_clients[interaction.guild_id]
        if not voice_client.is_connected:
            await interaction.response.send_message(content='No bot in voice channel', ephemeral=True, delete_after=3)
            return
        await self._remove_view_and_disconnect(voice_client=voice_client)
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

        voice_client: WavelinkPlayer = self.voice_clients[interaction.guild_id]
        if voice_client.is_connected:
            await voice_client.set_volume(value)
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

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEventPayload) -> None:
        """
        Callback function used for players to play next audio source in queue
        """
        voice_client: WavelinkPlayer = payload.player
        guild_id = payload.player.guild.id

        # since we let the track finish we make sure interrupted_time is cleared
        if payload.reason == 'FINISHED':
            await voice_client.track_finished()
            view = self.views.get(guild_id)
            if view:
                await view.replace_message(voice_client)
        # lets the task waiting for this signal continue.
        await self._set_track_state_change_signal(guild_id=guild_id)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackEventPayload) -> None:
        """
        Callback used when new track starts playing
        """
        guild_id = payload.player.guild.id
        # lets the task waiting for this signal continue.
        await self._set_track_state_change_signal(guild_id=guild_id)

    def get_view(self, interaction: discord.Interaction) -> PlayerControlView:
        """
        returns view acording to given interraction\n
        if view doesnt exist it creates it and then returns it
        """
        guild_id = interaction.guild_id
        channel = interaction.channel
        if not (view := self.views.get(guild_id, None)):
            view = PlayerControlView(self.bot, channel)
            self.views[guild_id] = view
        return view

    async def disconnect_if_alone(self, guild_id: int, delay: int = 2):
        """
        removes a view from given guild and disconnects
        """
        await asyncio.sleep(delay)
        voice_client: WavelinkPlayer = self.voice_clients[guild_id]
        if voice_client.channel and voice_client.is_connected and len(voice_client.channel.members) == 1:
            await self._remove_view_and_disconnect(voice_client)

    async def _remove_view_and_disconnect(self, voice_client: WavelinkPlayer):
        guild_id = voice_client.guild.id
        await voice_client.disconnect()
        if view := self.views.get(guild_id):
            view.remove_view()
            self.views.pop(guild_id)

    async def _set_track_state_change_signal(self, *, guild_id: int, active_time: int = 1):
        """
        Sets the track end signal for given guild
        """
        self.track_state_change[guild_id].set()
        await asyncio.sleep(active_time)
        self.track_state_change[guild_id].clear()
