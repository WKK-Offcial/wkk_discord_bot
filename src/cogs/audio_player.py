from __future__ import annotations

import asyncio
import datetime
import logging
import re
from io import BytesIO
from typing import TYPE_CHECKING, Callable

import discord
import wavelink
from discord import app_commands
from discord.ext import commands
from utils.endpoints import Endpoints

if TYPE_CHECKING:
    from main import BoiBot


def ChannelControlCheck(func):
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("dupa")

        bot_vc, user_vc = interaction.guild.voice_client, interaction.user.voice
        if not (bot_vc and user_vc and bot_vc.channel.id == user_vc.channel.id):
            await interaction.response.send_message("You can't control the bot because you're not on the voice channel",
                                                    delete_after=3, ephemeral=True)
            return
        await func(*args, **kwargs)

    return decorator



class AudioPlayer(commands.Cog):
    """
    Class for music commands.
    self.states is dictionary that holds handle to a player context (in particular, controllable player view)
    {guild_id:state}
    """

    def __init__(self, bot: BoiBot) -> None:
        self.bot: BoiBot = bot
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
            await interaction.edit_original_response(content="You're not in voice channel")
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
        self.states.pop(guild_id)

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


class PlayerState:
    """
    Contains custom state related to the player
    """
    def __init__(self, bot_vc: wavelink.Player, guild_id: int, bot: BoiBot, cleanup: Callable[[], None]):
        self.active_view: PlayerView = None
        self.bot_vc: wavelink.Player = bot_vc
        self.guild_id: int = guild_id
        self.last_text_channel_used: discord.TextChannel = None
        self.bot = bot
        self.killed = False
        self.cleanup = cleanup

    async def transit_to_stopped_no_users(self) -> None:
        """
        Player stopped because all users left the channel
        """
        if self.killed:
            return
        self._destroy_current_embed()
        self.active_view = PlayerNoMoreUsersView(self)
        await self.active_view.send_embed(self.last_text_channel_used)
        self._cleanup_self()

    async def create_control_view_if_does_not_exist(self, text_channel: discord.TextChannel) -> None:
        """
        Create control view
        """
        if self.killed:
            return
        self._destroy_current_embed()
        self.active_view = PlayerControlView(self)
        self.last_text_channel_used = text_channel
        await self.active_view.send_embed(text_channel)

    async def resend_control_view(self) -> None:
        """
        Send control view again
        """
        if self.killed:
            return
        self._destroy_current_embed()
        self.active_view = PlayerControlView(self)
        await self.active_view.send_embed(self.last_text_channel_used)

    async def transit_to_queue_ended(self) -> None:
        """
        Player stopped because the queue has ended
        """
        if self.killed:
            return
        self._destroy_current_embed()
        self.active_view = PlayerEndedView(self)
        await self.active_view.send_embed(self.last_text_channel_used)
        # currently there is no sense to do anything for this view, but there will be an undo button here
        self._cleanup_self()

    def _destroy_current_embed(self) -> None:
        if self.active_view is not None:
            self.active_view.stop()
            self.active_view.remove_embed()

    def _cleanup_self(self) -> None:
        self.active_view.stop()
        self.killed = True
        self.cleanup()


class PlayerView(discord.ui.View):
    def __init__(self, player_state: PlayerState):
        super().__init__(timeout=None)
        self.embed_handle: discord.Message = None
        self.player_state = player_state

    def remove_embed(self) -> None:
        """
        Removes embed with audio player information
        """
        if self.embed_handle:
            coro = self.embed_handle.delete()
            self.stop()
            self.clear_items()
            asyncio.run_coroutine_threadsafe(coro, self.player_state.bot.loop)

    async def send_embed(self, text_channel: discord.TextChannel) -> None:
        """
        Removes last message and sends new one to keep it on the bottom of the chat
        """
        if self.embed_handle:
            await self.embed_handle.delete()

        self.embed_handle = await self.make_embed(text_channel)

    async def make_embed(self, channel) -> discord.Embed:
        raise NotImplementedError("Should be overriden")

    async def _add_footer(self, embed) -> None:
        embed.set_footer(text='2137',
                         icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')

    async def _generate_embed_with_defaults(self) -> discord.Embed:
        return discord.Embed(title='The Boi',
                             color=0x00ff00,
                             timestamp=datetime.datetime.now(datetime.timezone.utc))


class PlayerNoMoreUsersView(PlayerView):
    """
    View class for after all the users have left the channel
    """

    def __init__(self, player_state: PlayerState):
        super().__init__(player_state)

    async def make_embed(self, channel) -> discord.Embed:
        embed = await self._generate_embed_with_defaults()
        embed.add_field(name='All users have left the channel', value=':(', inline=True)
        await self._add_footer(embed)
        return await channel.send(content=None, embed=embed, view=self)


class PlayerEndedView(PlayerView):
    """
    View class for after the queue has ended and no song is playing
    """

    def __init__(self, player_state: PlayerState):
        super().__init__(player_state)

    async def make_embed(self, channel) -> discord.Embed:
        embed = await self._generate_embed_with_defaults()
        embed.add_field(name='Nothing is being played. The queue has ended.', value=':(', inline=True)
        await self._add_footer(embed)
        return await channel.send(content=None, embed=embed, view=self)


class PlayerControlView(PlayerView):
    """
    View class for controlling audio player through view
    """

    def __init__(self, player_state: PlayerState):
        super().__init__(player_state)

    @discord.ui.button(label='▶▶ Skip', style=discord.ButtonStyle.blurple)
    @ChannelControlCheck
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Skip track on button press
        """
        bot_vc: wavelink.Player = interaction.guild.voice_client

        if bot_vc.is_playing():
            await bot_vc.stop()
            await interaction.response.defer()
        else:
            await interaction.response.send_message("Nothing is playing right now",
                                                    delete_after=3, ephemeral=True)

    @discord.ui.button(label='❚❚ Pause', style=discord.ButtonStyle.blurple)
    @ChannelControlCheck
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Pause/resume the player on button press
        """
        bot_vc: wavelink.Player = interaction.guild.voice_client

        if not bot_vc.is_paused():
            await bot_vc.pause()
            button.label = '▶ Resume'
        else:
            await bot_vc.resume()
            button.label = '❚❚ Pause'
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label='▮ Stop', style=discord.ButtonStyle.red)
    @ChannelControlCheck
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Stop track on button press
        """
        bot_vc: wavelink.Player = interaction.guild.voice_client

        if bot_vc.is_playing():
            bot_vc.queue.clear()
            await bot_vc.stop()
            await interaction.response.defer()
        else:
            await interaction.response.send_message("Nothing is playing right now",
                                                    delete_after=3, ephemeral=True)

    @discord.ui.button(label='ඞ', style=discord.ButtonStyle.grey)
    @ChannelControlCheck
    async def filter(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        fourth density
        """
        bot_vc: wavelink.Player = interaction.guild.voice_client
        user_vc = interaction.user.voice
        if not (bot_vc and user_vc and bot_vc.channel.id == user_vc.channel.id):
            await interaction.response.send_message("You cannot control the bot (check voice channel)",
                                                    delete_after=3, ephemeral=True)
            return
        if bot_vc.is_playing():
            filter_ = wavelink.Filter(
                tremolo=wavelink.Tremolo(frequency=4, depth=0.3),
                vibrato=wavelink.Vibrato(frequency=14, depth=1),
                timescale=wavelink.Timescale(pitch=0.8)
            )
            no_filter = wavelink.Filter()
            await bot_vc.set_filter(no_filter if bot_vc.filter else filter_)
            button.label = '' if bot_vc.filter else 'ඞ'
            button.emoji = discord.PartialEmoji.from_str('<a:amogus:1088546951949209620>') if bot_vc.filter else None
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("Nothing is playing right now",
                                                    delete_after=3, ephemeral=True)

    async def make_embed(self, text_channel) -> discord.Embed:
        # Calculate queue time length
        bot_vc = self.player_state.bot_vc
        now_playing = bot_vc.current
        total_seconds = 0
        for i in range(bot_vc.queue.count):
            total_seconds += bot_vc.queue[i].length / 1000
        minutes = divmod(total_seconds, 60)[0]
        hours, minutes = divmod(minutes, 60)
        queue_time = f'⌛ {int(hours):02d} hr {int(minutes):02d} min'
        minutes, secs = divmod(now_playing.length / 1000, 60)
        now_playing_time = f'⌛ {int(minutes):02d} min {int(secs):02d} s'

        # Prepare queue list
        queue_preview = ''
        if bot_vc.queue.count > 10:
            for i in range(10):
                queue_preview += f"{i + 1}. {str(bot_vc.queue[i].title)}\n"
            queue_preview += f'... and {bot_vc.queue.count - 10} more.\n{queue_time}\n'
        else:
            for i in range(bot_vc.queue.count):
                queue_preview += f"{str(bot_vc.queue[i].title)}\n"
            queue_preview += f'{queue_time}\n'

        # Create new embed
        embed = await self._generate_embed_with_defaults()
        if bot_vc.queue.count > 0:
            embed.add_field(name='Queue', value=queue_preview, inline=False)
        embed.add_field(name='Now Playing', value=f'{now_playing.title}\n{now_playing_time}', inline=True)
        embed.add_field(name='', value='▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁', inline=False)
        await self._add_footer(embed)
        thumbnail = await wavelink.YouTubeTrack.fetch_thumbnail(now_playing)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        return await text_channel.send(content=None, embed=embed, view=self)
