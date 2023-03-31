from __future__ import annotations

import logging
import re
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
        self.views: dict[int, PlayerControlView] = {}
        self.history: dict[int, list[tuple[wavelink.Playable, int]]] = {}
        self.voice_clients: dict[int, WavelinkPlayer] = {}

    def init_voice_client(self):
        for guild in self.bot.guilds:
            vc = WavelinkPlayer(self.bot, guild.voice_channels[0])
            guild_id = guild.id
            self.voice_clients[guild_id] = vc

    #

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
        # voice_channel.connect()

        # Connect to vc or change vc to the one caller is in
        voice_player: WavelinkPlayer = self.voice_clients[guild_id]
        await voice_player.connect_and_move_to(voice_channel)
        try:
            tracks = await voice_player.search_and_play(search, force_play=force_play)
            await interaction.edit_original_response(content=f"Found \"{tracks[0].title}\".")

            # Get/create view with audio controls
            view = self.views.get(guild_id)
            if not view or not view.active:
                view = PlayerControlView(self.bot, guild_id, interaction.channel)
                self.views[guild_id] = view
            elif not view.controls_enabled:
                view.enable_control_buttons()
            if voice_player.history.count == 0:
                view.undo_button.disabled = True

            await view.send_embed(voice_player)

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
        bot_vc: WavelinkPlayer = interaction.guild.voice_client
        if not bot_vc:
            await interaction.response.send_message(content='No bot in voice channel', ephemeral=True, delete_after=3)
            return
        await self._remove_view_and_disconnect(bot_vc=bot_vc)
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

        bot_vc: WavelinkPlayer = interaction.guild.voice_client
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
        bot_vc: WavelinkPlayer = payload.player
        guild_id = bot_vc.guild.id
        view = self.views.get(guild_id)

        # REPLACED means it was called from undo_button so we only need to update embed
        if payload.reason == "REPLACED":
            # Disable undo button if there's nothing to undo
            if bot_vc.history.count == 0:
                view.undo_button.disabled = True
            if not view.controls_enabled:
                view.enable_control_buttons()
            await view.send_embed(bot_vc)
            return

        # Queue logic
        bot_vc.history.put_at_front(payload.track)
        guild_queue = bot_vc.queue
        if guild_queue.count > 0:
            # Play next in queue
            next_audio_track = await guild_queue.get_wait()
            track_start_time = bot_vc.track_start_times.get(next_audio_track.title, 0)
            await bot_vc.play(next_audio_track, start=track_start_time)
            # Update view
            if not view.controls_enabled:
                view.enable_control_buttons()
            view.undo_button.disabled = False
            await view.send_embed(bot_vc)

        elif view:
            # Update view
            await bot_vc.set_filter(wavelink.Filter())
            view.disable_control_buttons()
            view.undo_button.disabled = False
            await view.send_embed(bot_vc)

    async def disconnect_when_alone(self, guild_id):
        """
        removes a view from given guild
        """
        # this check is performed once when reciving "on_voice_state_update"
        # then once again here to give user the grace period before disconecting
        bot_vc: WavelinkPlayer = self.bot.get_guild(guild_id).voice_client
        if bot_vc and len(bot_vc.channel.members) == 1:
            await self._remove_view_and_disconnect(bot_vc)

    async def _remove_view_and_disconnect(self, bot_vc: WavelinkPlayer):
        guild_id = bot_vc.guild.id
        bot_vc: WavelinkPlayer = self.bot.get_guild(guild_id).voice_client
        await bot_vc.disconnect()
        if view := self.views.get(guild_id):
            view.remove_view()
            self.views.pop(guild_id)

    async def _search_track(self, search: str, bot_vc: WavelinkPlayer) -> tuple[list[wavelink.Playable] | None, int]:
        """
        Creates audio tracks and adds it to queue
        Returns first audio track and start time
        """
        guild_id = bot_vc.guild.id
        start_time: int = 0
        # Check if user wants to play audio from YouTube Playlist...
        try:
            youtube_playlist_regex = re.search(r"list=([^#\&\?]*).*", search)
            if youtube_playlist_regex and youtube_playlist_regex.groups():
                safe_url = f'https://www.youtube.com/playlist?list={youtube_playlist_regex.groups()[0]}'
                playlist = await wavelink.YouTubePlaylist.search(safe_url, return_first=True)
                audio_tracks = [track for track in playlist.tracks]
            # ...or soundboard...
            elif search.isdecimal():
                sound_id = int(search)
                guild_soundboard = Endpoints.get_soundboard(guild_id)
                if not guild_soundboard or sound_id > len(guild_soundboard):
                    return None

                file_name = guild_soundboard[int(search) - 1]
                file_path = f'sounds/{str(guild_id)}/{file_name}'
                audio_tracks = [await wavelink.GenericTrack.search(file_path, return_first=True)]
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
                    audio_tracks = [await wavelink.YouTubeTrack.search(safe_url, return_first=True)]
                else:
                    audio_tracks = [await wavelink.YouTubeTrack.search(search, return_first=True)]

            return audio_tracks, start_time
        except wavelink.exceptions.NoTracksError:
            return None
