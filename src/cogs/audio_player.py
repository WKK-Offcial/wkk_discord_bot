from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re
from io import BytesIO
from typing import TYPE_CHECKING

import discord
import wavelink
import yt_dlp
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from main import BoiBot


class AudioPlayer(commands.Cog):
    """
    Class for music commands.
    self.views is dictionary that holds handle to a message with audio controls view {guild_id:view},
    """

    def __init__(self, bot: BoiBot) -> None:
        self.bot: BoiBot = bot
        self.views: dict[int, AudioControls] = {}

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEventPayload) -> None:
        """
        Callback function used for players to play next audio source in queue
        """
        guild_id = payload.player.guild.id
        voice_client = payload.player
        view = self.views.get(guild_id)
        guild_queue = voice_client.queue
        if guild_queue.count > 0:
            # Play next in queue
            next_audio_track = await guild_queue.get_wait()
            await voice_client.play(next_audio_track)
            # Update embed
            await view._send_embed(voice_client)
        else:
            if view:
                view._remove_embed()
                self.views.pop(guild_id)

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
            await interaction.edit_original_response(content="You're not in voice channel")
            return

        # Connect to vc or change vc to the one caller is in
        voice_client: wavelink.Player = interaction.guild.voice_client
        if not voice_client:
            voice_client = await voice_channel.connect(cls=wavelink.Player)
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        try:
            search_result = await self._add_to_queue(search, voice_client)
            await interaction.edit_original_response(content=f"Found \"{search_result.title}\".")

            if not voice_client.is_playing():
                first_in_queue = await voice_client.queue.get_wait()
                await voice_client.play(first_in_queue)

            # Get/create view with audio controls
            view = self.views.get(guild_id)
            if not view or not view.active:
                view = AudioControls(self.bot, guild_id, interaction.channel)
                self.views[guild_id] = view
            await view._send_embed(voice_client)

        # Catch errors
        except SyntaxError:
            await interaction.edit_original_response(content='No argument passed!')
            logging.error(SyntaxError.msg)
        except IndexError:
            await interaction.edit_original_response(content='Index out of range!')
            logging.error(IndexError)
        except TypeError:
            await interaction.edit_original_response(content="Type error!")
            logging.error(TypeError)
        except yt_dlp.utils.ExtractorError:
            logging.error(yt_dlp.utils.ExtractorError.msg)
            await interaction.edit_original_response(content=f"\"{search}\" not available.")

    async def _add_to_queue(self, search: str, voice_client: wavelink.Player) -> wavelink.Playable:
        """
        Creates audio tracks and adds it to queue
        """
        guild_id = voice_client.guild.id
        found_playlist = re.search(r"^.*youtu.be\/|list=([^#\&\?]*).*", search)
        # Check if user wants to play audio from YouTube Playlist...
        if found_playlist:
            playlist = await wavelink.YouTubePlaylist.search(found_playlist.groups()[0], return_first=True)
            for track in playlist.tracks:
                await voice_client.queue.put_wait(track)
            audio_track = playlist.tracks[0]
        # ...or soundboard...
        elif search.isnumeric():
            guild_soundboard = self.bot.get_soundboard(guild_id)
            file_name = guild_soundboard[int(search) - 1]
            file_path = os.path.abspath(f'cache/soundboards/{str(guild_id)}/{file_name}')
            audio_track = await wavelink.GenericTrack.search(file_path, return_first=True)
            await voice_client.queue.put_wait(audio_track)
        # ...or Youtube track.
        else:
            audio_track = await wavelink.YouTubeTrack.search(search, return_first=True)
            await voice_client.queue.put_wait(audio_track)
        return audio_track

    @app_commands.command(name='disconnect')
    async def disconnect(self, interaction: discord.Interaction) -> None:
        """
        Simple disconnect command.
        This command assumes there is a currently connected Player.
        """
        voice_client: wavelink.Player = interaction.guild.voice_client
        await voice_client.disconnect()
        await interaction.response.send_message(content='Bot disconnected')

    @app_commands.command(name="soundboard")
    async def list_soundboard(self, interaction: discord.Interaction):
        """
        Lists all audio files uploaded to soundboard
        """
        await interaction.response.send_message("Preparing list...")
        guild_soundboard = self.bot.get_soundboard(interaction.guild_id)
        message_content = "SOUNDBOARD\n"
        i = 0
        for entry in guild_soundboard:
            i += 1
            message_content += f'{i}. {entry}\n'

        file = discord.File(fp=BytesIO(message_content.encode("utf8")), filename="soundboard.cpp")
        await interaction.edit_original_response(content='', attachments=[file])

    @app_commands.command(name="upload")
    async def upload_audio(self, interaction: discord.Interaction, mp3_file: discord.Attachment):
        """
        Upload audio file to soundboard
        """
        await interaction.response.send_message("Processing file...")

        if not mp3_file.filename.endswith(".mp3"):
            await interaction.edit_original_response(content='Audio files must have .mp3 format')
            return

        save_location = f"./cache/soundboards/{interaction.guild_id}/{mp3_file.filename}"
        await mp3_file.save(save_location)
        self.bot.dropbox.upload_file(save_location, interaction.guild_id)
        self.bot.add_to_soundboard(interaction.guild_id, mp3_file.filename)
        await interaction.edit_original_response(content=f'Successfully uploaded {mp3_file.filename}')


class AudioControls(discord.ui.View):
    """
    View class for controlling audio player through view
    """

    def __init__(self, bot: BoiBot, guild_id: int, text_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.bot: BoiBot = bot
        self.guild_id: int = guild_id
        self.text_channel: discord.TextChannel = text_channel
        self.embed_handle: discord.Message = None
        self.active = True

    def _remove_embed(self):
        """
        Removes embed with audio player information
        """
        if self.embed_handle:
            coro = self.embed_handle.delete()
            self.stop()
            self.clear_items()
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    async def _send_embed(self, voice_client: wavelink.Player):
        """
        Removes last message and sends new one to keep it on the bottom of the chat
        """
        if self.embed_handle:
            await self.embed_handle.delete()

        # Get queue
        now_playing = voice_client.current
        queue_preview = ''
        if voice_client.queue.count > 10:
            for i in range(10):
                queue_preview += f"{str(voice_client.queue[i].title)}\n"
            queue_preview += f'... and {voice_client.queue.count - 10} more.'
        else:
            for i in range(voice_client.queue.count - 1):
                queue_preview += f"{str(voice_client.queue[i].title)}\n"

        # Create new embed
        embed = discord.Embed(title='The Boi',
                              color=0x00ff00,
                              timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name='Queue', value=queue_preview, inline=False)
        embed.add_field(name='Now Playing', value=f'{now_playing.title}', inline=True)
        embed.set_footer(text='2137',
                         icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
        if now_playing.thumbnail:
            embed.set_thumbnail(url=now_playing.thumbnail)

        self.embed_handle = await self.text_channel.send(content=None, embed=embed, view=self)

    @discord.ui.button(label='Skip', style=discord.ButtonStyle.green)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        When skip button is pressed skip current audio
        """
        button.is_persistent()  # Useless - pylint about button not being used otherwise
        voice_client: wavelink.Player = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            await voice_client.stop()
            await interaction.response.defer()
        else:
            await interaction.response.send_message("Nothing is playing right now", delete_after=1)

    @discord.ui.button(label='Stop', style=discord.ButtonStyle.red)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        When stop button is pressed stop audio playback and clear queue
        """
        button.is_persistent()  # Useless - pylint about button not being used otherwise
        voice_client: wavelink.Player = interaction.guild.voice_client

        if voice_client and voice_client.is_playing():
            voice_client.queue.clear()
            await voice_client.stop()
            await interaction.response.defer()
        else:
            await interaction.response.send_message("Nothing is playing right now", delete_after=1)

        self._remove_embed()
        self.stop()
        self.active = False

    @discord.ui.button(label='Vol+', style=discord.ButtonStyle.gray)
    async def volume_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Volume up by 10%
        """
        button.is_persistent()  # Useless - pylint about button not being used otherwise
        voice_client: wavelink.Player = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            new_volume = min(voice_client.volume + 20, 100)
            await voice_client.set_volume(new_volume)
            if new_volume == 100:
                button.disabled = True
            self.volume_down_button.disabled = False
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label='Vol-', style=discord.ButtonStyle.gray)
    async def volume_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Volume down by 10%
        """
        voice_client: wavelink.Player = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            new_volume = max(voice_client.volume - 20, 0)
            await voice_client.set_volume(new_volume)
            if new_volume == 0:
                button.disabled = True
            self.volume_up_button.disabled = False
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()
