from __future__ import annotations

import asyncio
import datetime
import logging
import re
from io import BytesIO
from typing import TYPE_CHECKING, Callable

import discord
import wavelink

if TYPE_CHECKING:
    from main import DiscordBot

def channel_control_check(func):
    """
    Decorator used to check whether player is able to use audio player controls.
    (Must be in the same voice channel)
    Executes decorated function only if check passed
    """
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("Interaction is None")

        bot_vc, user_vc = interaction.guild.voice_client, interaction.user.voice
        if not (bot_vc and user_vc and bot_vc.channel.id == user_vc.channel.id):
            await interaction.response.send_message("You can't control the bot because you're not on the voice channel",
                                                    delete_after=3, ephemeral=True)
            return
        await func(*args, **kwargs)

    return decorator

def is_playing_check(func):
    """
    Decorator for checking if bot is playing something.
    Executes decorated function only if check passed
    """
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("Interaction is None")

        bot_vc = interaction.guild.voice_client
        if not bot_vc.is_playing():
            await interaction.response.send_message("Nothing is playing right now",
                                                        delete_after=3, ephemeral=True)
            return
        await func(*args, **kwargs)
    return decorator

class PlayerState:
    """
    Contains custom state related to the player
    """
    def __init__(self, bot_vc: wavelink.Player, guild_id: int, bot: DiscordBot, cleanup: Callable[[], None]):
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
        self._cleanup_self() # <- second call to pop, raises exception

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

    async def make_embed(self, text_channel: discord.TextChannel) -> discord.Embed:
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

    async def make_embed(self, text_channel: discord.TextChannel) -> discord.Embed:
        embed = await self._generate_embed_with_defaults()
        embed.add_field(name='All users have left the channel', value=':(', inline=True)
        await self._add_footer(embed)
        return await text_channel.send(embed=embed, view=self, delete_after=60)


class PlayerEndedView(PlayerView):
    """
    View class for after the queue has ended and no song is playing
    """

    def __init__(self, player_state: PlayerState):
        super().__init__(player_state)

    async def make_embed(self, text_channel: discord.TextChannel) -> discord.Embed:
        embed = await self._generate_embed_with_defaults()
        embed.add_field(name='Nothing is being played. The queue has ended.', value='', inline=True)
        await self._add_footer(embed)
        return await text_channel.send(embed=embed, view=self, delete_after=60)


class PlayerControlView(PlayerView):
    """
    View class for controlling audio player through view
    """

    def __init__(self, player_state: PlayerState):
        super().__init__(player_state)

    @discord.ui.button(label='▶▶ Skip', style=discord.ButtonStyle.blurple)
    @channel_control_check
    @is_playing_check
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Skip track on button press
        """
        bot_vc: wavelink.Player = interaction.guild.voice_client
        await bot_vc.stop()
        await interaction.response.defer()

    @discord.ui.button(label='❚❚ Pause', style=discord.ButtonStyle.blurple)
    @channel_control_check
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
    @channel_control_check
    @is_playing_check
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Stop track on button press
        """
        bot_vc: wavelink.Player = interaction.guild.voice_client
        bot_vc.queue.clear()
        await bot_vc.stop()
        await interaction.response.defer()

    @discord.ui.button(label='ඞ', style=discord.ButtonStyle.grey)
    @channel_control_check
    @is_playing_check
    async def filter(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        fourth density
        """
        bot_vc: wavelink.Player = interaction.guild.voice_client
        filter_ = wavelink.Filter(tremolo=wavelink.Tremolo(frequency=4, depth=0.3),
                                  vibrato=wavelink.Vibrato(frequency=14, depth=1),
                                  timescale=wavelink.Timescale(pitch=0.8))
        no_filter = wavelink.Filter()
        await bot_vc.set_filter(no_filter if bot_vc.filter else filter_)
        button.label = '' if bot_vc.filter else 'ඞ'
        button.emoji = discord.PartialEmoji.from_str('<a:amogus:1088546951949209620>') if bot_vc.filter else None
        await interaction.response.edit_message(view=self)

    async def make_embed(self, text_channel: discord.TextChannel) -> discord.Embed:
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
        return await text_channel.send(embed=embed, view=self)
