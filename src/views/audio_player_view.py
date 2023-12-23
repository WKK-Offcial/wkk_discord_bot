from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands
from audio_player import AudioPlayer

from utils.decorators import (
    button_cooldown,
    is_playing_check,
    user_bot_in_same_channel_check,
)

if TYPE_CHECKING:
    from cogs.audio_cog import AudioCog
    from main import DiscordBot


NOTHING_IN_QUEUE_PLACEHOLDER = 'Nothing in current queue.'
MAX_SELECT_LEN = 25

class AudioPlayerView(discord.ui.View):
    """
    View class for controlling audio player through view
    """

    def __init__(self, bot: DiscordBot, text_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.bot: DiscordBot = bot
        self.text_channel: discord.TextChannel = text_channel
        self.message_handle: discord.Message | None = None
        self.queue_page: int = 0
        self._cooldown = commands.CooldownMapping.from_cooldown(rate=1, per=1, type=commands.BucketType.channel)

    def __del__(self):
        try:
            coro = self.message_handle.delete()
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
        except AttributeError:
            pass

    def remove_view(self):
        """
        Removes embed with audio player information
        """
        if self.message_handle:
            coro = self.message_handle.delete()
            self.stop()
            self.clear_items()
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    async def send_embed(self):
        """
        Removes last message and sends new one to keep it on the bottom of the chat\n
        """
        embed = await self.__prepare_embed()
        self._update_buttons_state()
        if self.message_handle:
            await self.message_handle.delete()
        self.message_handle = await self.text_channel.send(content=None, embed=embed, view=self)


    @discord.ui.button(label='◀◀ Prev', style=discord.ButtonStyle.blurple, row=0)
    @user_bot_in_same_channel_check
    @button_cooldown
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Play previous track.
        """
        player = cast(AudioPlayer, interaction.guild.voice_client)
        await player.play_previous_track()
        await interaction.response.defer()

    @discord.ui.button(label='❚❚ Pause', style=discord.ButtonStyle.blurple, row=0)
    @user_bot_in_same_channel_check
    @button_cooldown
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Pause/resume the player on button press
        """
        player = cast(AudioPlayer, interaction.guild.voice_client)
        await player.pause(not player.paused)
        await interaction.response.defer()
        await self._update_embed()

    @discord.ui.button(label='▶▶ Skip', style=discord.ButtonStyle.blurple, row=0)
    @user_bot_in_same_channel_check
    @is_playing_check
    @button_cooldown
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Skip track on button press
        """
        player = cast(AudioPlayer, interaction.guild.voice_client)
        await player.skip()
        await interaction.response.defer()

    @discord.ui.button(label='▮ Stop', style=discord.ButtonStyle.red, row=0)
    @user_bot_in_same_channel_check
    @is_playing_check
    @button_cooldown
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Stop track on button press
        """
        player = cast(AudioPlayer, interaction.guild.voice_client)
        player.queue.clear()
        await player.skip()
        await player.disable_filters()
        await interaction.response.defer()

    @discord.ui.button(label='ඞ', style=discord.ButtonStyle.grey, row=0)
    @user_bot_in_same_channel_check
    @is_playing_check
    async def filter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Filter to toggle audio filters
        """
        player = cast(AudioPlayer, interaction.guild.voice_client)
        await player.toggle_nightcore_filter()
        await interaction.response.defer()
        await self._update_embed()

    @discord.ui.select(
        cls=discord.ui.Select,
        options=[discord.SelectOption(label=NOTHING_IN_QUEUE_PLACEHOLDER)],
        placeholder=NOTHING_IN_QUEUE_PLACEHOLDER,
        max_values=1,
        min_values=1,
        disabled=True,
        row=1,
    )
    @user_bot_in_same_channel_check
    async def queue_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """
        Allows selecting song from the queue and playing it
        """
        player = cast(AudioPlayer, interaction.guild.voice_client)
        index = int(select.values[0])
        if self.queue_page > 0:
            await player.play_track_from_queue(index)
        else:
            await player.play_track_from_history(index)

        await interaction.response.defer()

    @discord.ui.button(label='◀', style=discord.ButtonStyle.grey, row=2, disabled=True)
    @user_bot_in_same_channel_check
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Loads previous page in the select window
        """
        self.queue_page -= 1
        self._prepare_track_selection_list()
        await interaction.response.defer()
        await self._update_embed()

    @discord.ui.button(label='▶', style=discord.ButtonStyle.grey, row=2, disabled=True)
    @user_bot_in_same_channel_check
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Loads next page in the select window
        """
        self.queue_page += 1
        self._prepare_track_selection_list()
        await interaction.response.defer()
        await self._update_embed()

    async def __prepare_embed(self) -> discord.Embed:
        """
        returns embed based on current state of voice_client
        """
        # Calculate queue time length
        total_seconds = 0
        player = cast(AudioPlayer, self.text_channel.guild.voice_client)
        for i, track in enumerate(player.queue):
            total_seconds += track.length / 1000
        minutes = divmod(total_seconds, 60)[0]
        hours, minutes = divmod(minutes, 60)
        queue_time = f'⌛ {int(hours):02d} hr {int(minutes):02d} min'

        now_playing = player.current
        if now_playing:
            minutes, secs = divmod(now_playing.length / 1000, 60)
            now_playing_time = f'⌛ {int(minutes):02d} min {int(secs):02d} s'

        # Prepare queue list
        queue_preview = ''
        if len(player.queue) > 10:
            for i in range(10):
                queue_preview += f"{i + 1}. {str(player.queue[i].title)}\n"
            queue_preview += f'... and {len(player.queue) - 10} more.\n{queue_time}\n'
        else:
            for i, track in enumerate(player.queue):
                queue_preview += f"{i + 1}. {str(track.title)}\n"
            queue_preview += f'{queue_time}\n'

        # Create new embed
        embed = discord.Embed(title='The Boi', color=0x00FF00, timestamp=datetime.datetime.now(datetime.timezone.utc))
        if len(player.queue) > 0:
            embed.add_field(name='Queue:', value=queue_preview, inline=False)
        if now_playing:
            embed.add_field(name='Now Playing:', value=f'{now_playing.title}\n{now_playing_time}', inline=True)
            thumbnail = now_playing.artwork
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
        else:
            embed.add_field(name='Nothing is playing right now', value=':(', inline=True)
        embed.add_field(name='', value='▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁', inline=False)
        embed.set_footer(text='2137', icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
        return embed

    async def _update_embed(self):
        """
        Updates embed contents (does not remove / send)
        """
        if not self.text_channel:
            return

        embed = await self.__prepare_embed()
        self._update_buttons_state()
        if self.message_handle:
            await self.message_handle.edit(view=self, embed=embed)

    def _prepare_track_selection_list(self):
        """
        calculates state of select window and related buttons
        """
        player = cast(AudioPlayer, self.text_channel.guild.voice_client)
        queue_len = len(player.queue)
        history_len = len(player.queue.history)
        max_pages = max(queue_len - 1, 0) // MAX_SELECT_LEN
        min_pages = -(max(history_len - 1, 0) // MAX_SELECT_LEN) - 1 if history_len else 0
        self.queue_page = min(max_pages, max(min_pages, self.queue_page))  # so page is correct on queue lenth change
        if self.queue_page >= 0:
            first_index = self.queue_page * MAX_SELECT_LEN + 1
            last_index = (self.queue_page + 1) * MAX_SELECT_LEN
        else:
            first_index = (-self.queue_page - 1) * MAX_SELECT_LEN + 1
            last_index = -self.queue_page * MAX_SELECT_LEN

        self.previous_page.disabled = self.queue_page <= min_pages
        self.next_page.disabled = self.queue_page >= max_pages
        # fmt: off
        self.queue_select.disabled = (
            not player.queue and self.queue_page >= 0) or (
            not player.queue.history and self.queue_page < 0
        )
        # fmt: on
        if player.queue and self.queue_page >= 0:  # display current queue
            self.queue_select.options = [
                discord.SelectOption(label=f'{index +1}.  {track.title}', value=str(index))
                for index, track in enumerate(player.queue)
                if index + 1 >= first_index and index < last_index
            ]
            self.queue_select.placeholder = (
                f'Displaying: {first_index}-{min(last_index,len(player.queue))} (current queue)'
            )
        elif self.queue_page < 0:  ## display history queue
            self.queue_select.options = [
                discord.SelectOption(label=f'{index +1}.  {track.title}', value=str(history_len - 1 - index))
                for index, track in enumerate(list(player.queue.history)[::-1])
                if index + 1 >= first_index and index < last_index
            ]
            self.queue_select.placeholder = (
                f'Displaying: {first_index}-{min(last_index,len(player.queue.history))} (history queue)'
            )
        else:
            self.queue_select.options = [discord.SelectOption(label=NOTHING_IN_QUEUE_PLACEHOLDER)]
            self.queue_select.placeholder = NOTHING_IN_QUEUE_PLACEHOLDER

    def _update_buttons_state(self):
        """
        calculates state of view
        """
        dancing_black_man = discord.PartialEmoji.from_str('<a:dance:1142174154917941400>')
        amogus = 'ඞ'

        player = cast(AudioPlayer, self.text_channel.guild.voice_client)
        self.previous_button.disabled = not len(player.queue.history) > 1
        self.pause_button.label = '▶ Resume' if player.paused else '❚❚ Pause'
        self.pause_button.disabled = not player.playing
        self.skip_button.disabled = not player.playing
        self.stop_button.disabled = not player.playing
        self.filter_button.disabled = not player.playing
        self.filter_button.label = amogus if not player.filters_applied else ''
        self.filter_button.emoji = dancing_black_man if player.filters_applied else None
        self._prepare_track_selection_list()
