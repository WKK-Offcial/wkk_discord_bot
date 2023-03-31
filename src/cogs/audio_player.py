from __future__ import annotations

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
from utils.wavelink_player import NoTracksFound, WavelinkPlayer
from views.audio_player_view import PlayerControlView

if TYPE_CHECKING:
    from main import DiscordBot


class AudioPlayer(commands.Cog):
    """
    Class for music commands.
    self.views is dictionary that holds handle to a message with audio controls view {guild_id:view},
    """

    def __init__(self, bot: DiscordBot) -> None:
        self.bot: DiscordBot = bot
        self.history: dict[int, list[tuple[wavelink.Playable, int]]] = {}
        self.voice_clients: dict[int, WavelinkPlayer] = {}
        self.views: dict[int, PlayerControlView] = {}

    def init_voice_client(self):
        """
        pupulate voice_client dictionary.\n
        Run this method after discord bot finished setting up
        """
        # TODO dick comprehension
        for guild in self.bot.guilds:
            self.voice_clients[guild.id] = WavelinkPlayer(self.bot, guild.voice_channels[0])

    @commands.cooldown(rate=1, per=1)
    @commands.guild_only()
    @app_commands.command(name="play")
    @user_is_in_voice_channel_check
    async def play(self, interaction: discord.Interaction, search: str, force_play: bool | None) -> None:
        """
        For soundboard type audio ID from list. For YouTube type url or search phrase. Force ignores queue and plays song immediately
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
            await view.update_message(voice_player)

        # Catch errors
        except NoTracksFound:
            await interaction.edit_original_response(content=f"Couldn't find \"{search}\".")
        except SyntaxError as err:
            await interaction.edit_original_response(content='No argument passed!')
            logging.error(err.msg)
        except IndexError as err:
            await interaction.edit_original_response(content='Index out of range!')
            logging.error(err)
        except TypeError as err:
            await interaction.edit_original_response(content="Type error!")
            logging.error(err)
        except InvalidLavalinkResponse as err:
            # TODO: proper handling
            #      restarting bot worked last time it happened.
            #      check if simple reconnect to vc is enough if that happens again
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
        if not voice_client.is_connected():
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
        if voice_client.is_connected():
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
        guild_id = voice_client.guild.id
        view = self.views.get(guild_id)
        if view:
            await view.update_message(voice_client)

        # # # REPLACED means it was called from undo_button so we only need to update embed
        # # if payload.reason == "REPLACED":
        # #     # Disable undo button if there's nothing to undo
        # #     if voice_client.history.count == 0:
        # #         view.undo_button.disabled = True
        # #     if not view.controls_enabled:
        # #         view.enable_control_buttons()
        # #     await view.send_embed(voice_client)
        # #     return

        # # Queue logic
        # voice_client.history.put_at_front(payload.track)
        # guild_queue = voice_client.queue
        # if guild_queue.count > 0:
        #     # Play next in queue
        #     next_audio_track = await guild_queue.get_wait()
        #     track_start_time = voice_client.track_start_times.get(next_audio_track.title, 0)
        #     await voice_client.play(next_audio_track, start=track_start_time)
        #     # Update view
        #     if not view.controls_enabled:
        #         view.enable_control_buttons()
        #     view.undo_button.disabled = False
        #     await view.update_message(voice_client)

        # elif view:
        #     # Update view
        #     await voice_client.set_filter(wavelink.Filter())
        #     view.disable_control_buttons()
        #     view.undo_button.disabled = False
        #     await view.send_embed(voice_client)

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

    async def disconnect_if_alone(self, guild_id):
        """
        removes a view from given guild
        """
        # this check is performed once when reciving "on_voice_state_update"
        # then once again here to give user the grace period before disconecting
        voice_client: WavelinkPlayer = self.voice_clients[guild_id]
        if voice_client.is_connected() and len(voice_client.channel.members) == 1:
            await self._remove_view_and_disconnect(voice_client)

    async def _remove_view_and_disconnect(self, voice_client: WavelinkPlayer):
        guild_id = voice_client.guild.id
        voice_client: WavelinkPlayer = self.bot.get_guild(guild_id).voice_client
        await voice_client.disconnect()
        if view := self.views.get(guild_id):
            view.remove_view()
            self.views.pop(guild_id)
