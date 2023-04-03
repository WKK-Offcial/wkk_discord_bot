from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING

import discord
import wavelink
from discord.ext import commands

from utils.decorators import (
    button_cooldown,
    is_playing_check,
    run_threadsafe,
    user_bot_in_same_channel_check,
)

from .wavelink_player import WavelinkPlayer

if TYPE_CHECKING:
    from audio_cog import AudioCog

    from main import DiscordBot


NOTHING_IN_QUEUE_PLACEHOLDER = 'Nothing in current queue.'
MAX_SELECT_LEN = 25


class PlayerControlView(discord.ui.View):
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

    @discord.ui.button(label='◀◀ Prev', style=discord.ButtonStyle.blurple, row=0)
    @user_bot_in_same_channel_check
    @button_cooldown
    async def undo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Undo a song skip.
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await voice_client.previous()
        self.update_view_state(voice_client)
        embed = await self.calculate_embed(voice_client)
        coro = interaction.response.edit_message(view=self, embed=embed)
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    @discord.ui.button(label='❚❚ Pause', style=discord.ButtonStyle.blurple, row=0)
    @user_bot_in_same_channel_check
    @button_cooldown
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Pause/resume the player on button press
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await voice_client.toggle_pause()
        self.update_view_state(voice_client)
        coro = interaction.response.edit_message(view=self)
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    @discord.ui.button(label='▶▶ Skip', style=discord.ButtonStyle.blurple, row=0)
    @user_bot_in_same_channel_check
    @is_playing_check
    @button_cooldown
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Skip track on button press
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await voice_client.skip()
        await self.wait_for_track_end()
        self.update_view_state(voice_client)
        embed = await self.calculate_embed(voice_client)
        coro = interaction.response.edit_message(view=self, embed=embed)
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    @discord.ui.button(label='▮ Stop', style=discord.ButtonStyle.red, row=0)
    @user_bot_in_same_channel_check
    @is_playing_check
    @button_cooldown
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Stop track on button press
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await voice_client.stop_all()
        await self.wait_for_track_end()
        self.update_view_state(voice_client)
        embed = await self.calculate_embed(voice_client)
        coro = interaction.response.edit_message(view=self, embed=embed)
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    @discord.ui.button(label='ඞ', style=discord.ButtonStyle.grey, row=0)
    @user_bot_in_same_channel_check
    @is_playing_check
    async def filter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        fourth density
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await voice_client.toggle_cursed_filter()
        self.update_view_state(voice_client)
        coro = interaction.response.edit_message(view=self)
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

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
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await voice_client.play_from_queue(index=int(select.values[0]), history=self.queue_page < 0, force_play=True)
        await self.wait_for_track_end()
        self.update_view_state(voice_client)
        embed = await self.calculate_embed(voice_client)
        coro = interaction.response.edit_message(view=self, embed=embed)
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    @discord.ui.button(label='◀', style=discord.ButtonStyle.grey, row=2, disabled=True)
    @user_bot_in_same_channel_check
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        fourth density
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        self.queue_page -= 1
        self.update_select_state(voice_client)
        coro = interaction.response.edit_message(view=self)
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    @discord.ui.button(label='▶', style=discord.ButtonStyle.grey, row=2, disabled=True)
    @user_bot_in_same_channel_check
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        fourth density
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        self.queue_page += 1
        self.update_select_state(voice_client)
        coro = interaction.response.edit_message(view=self)
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    def update_view_state(self, voice_client: WavelinkPlayer):
        """
        calculates state of view
        """
        self.undo_button.disabled = voice_client.history.is_empty
        self.pause_button.disabled = not voice_client.current
        self.pause_button.label = '▶ Resume' if voice_client.is_paused() else '❚❚ Pause'
        self.skip_button.disabled = not voice_client.current
        self.stop_button.disabled = not voice_client.current
        self.filter_button.disabled = False
        self.filter_button.label = 'ඞ' if not voice_client.filter else ''
        self.filter_button.emoji = (
            discord.PartialEmoji.from_str('<a:amogus:1088546951949209620>') if voice_client.filter else None
        )
        self.update_select_state(voice_client)

    def update_select_state(self, voice_client: WavelinkPlayer):
        """
        calculates state of select window and related buttons
        """
        queue_len = len(voice_client.queue)
        history_len = len(voice_client.history)
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
            voice_client.queue.is_empty and self.queue_page >= 0) or (
            voice_client.history.is_empty and self.queue_page < 0
        )
        # fmt: on
        if not voice_client.queue.is_empty and self.queue_page >= 0:  # display current queue
            self.queue_select.options = [
                discord.SelectOption(label=f'{index +1}.  {track.title}', value=str(index))
                for index, track in enumerate(voice_client.queue)
                if index + 1 >= first_index and index < last_index
            ]
            self.queue_select.placeholder = (
                f'Displaying: {first_index}-{min(last_index,len(voice_client.queue))} (current queue)'
            )
        elif self.queue_page < 0:  ## display history queue
            self.queue_select.options = [
                discord.SelectOption(label=f'{index +1}.  {track.title}', value=str(history_len - 1 - index))
                for index, track in enumerate(list(voice_client.history)[::-1])
                if index + 1 >= first_index and index < last_index
            ]
            self.queue_select.placeholder = (
                f'Displaying: {first_index}-{min(last_index,len(voice_client.history))} (history queue)'
            )
        else:
            self.queue_select.options = [discord.SelectOption(label=NOTHING_IN_QUEUE_PLACEHOLDER)]
            self.queue_select.placeholder = NOTHING_IN_QUEUE_PLACEHOLDER

    async def wait_for_track_end(self) -> None:
        """
        waits for the current track to end.\n
        Useful because calling e.g. voice_client.skip() doesn't immidiately update voice_client correctly
        so this helps ensure that update_buttons() will give correct result
        """
        guild_id = self.text_channel.guild.id
        audio_player_cog: AudioCog = self.bot.cogs["AudioCog"]
        signal = audio_player_cog.track_state_change.get(guild_id)
        try:
            await asyncio.wait_for(signal.wait(), timeout=2)  # just to make sure it doesnt wait forever
            signal.clear()
        except TimeoutError:
            logging.warning('Timed out.')

    def remove_view(self):
        """
        Removes embed with audio player information
        """
        if self.message_handle:
            coro = self.message_handle.delete()
            self.stop()
            self.clear_items()
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    async def calculate_embed(self, voice_client: WavelinkPlayer) -> discord.Embed:
        """
        returns embed based on current state of voice_client
        """
        # Calculate queue time length
        total_seconds = 0
        for i in range(voice_client.queue.count):
            total_seconds += voice_client.queue[i].length / 1000
        minutes = divmod(total_seconds, 60)[0]
        hours, minutes = divmod(minutes, 60)
        queue_time = f'⌛ {int(hours):02d} hr {int(minutes):02d} min'

        now_playing = voice_client.current
        if now_playing:
            minutes, secs = divmod(now_playing.length / 1000, 60)
            now_playing_time = f'⌛ {int(minutes):02d} min {int(secs):02d} s'

        # Prepare queue list
        queue_preview = ''
        if voice_client.queue.count > 10:
            for i in range(10):
                queue_preview += f"{i + 1}. {str(voice_client.queue[i].title)}\n"
            queue_preview += f'... and {voice_client.queue.count - 10} more.\n{queue_time}\n'
        else:
            for i in range(voice_client.queue.count):
                queue_preview += f"{i + 1}. {str(voice_client.queue[i].title)}\n"
            queue_preview += f'{queue_time}\n'

        # Create new embed
        embed = discord.Embed(title='The Boi', color=0x00FF00, timestamp=datetime.datetime.now(datetime.timezone.utc))
        if voice_client.queue.count > 0:
            embed.add_field(name='Queue:', value=queue_preview, inline=False)
        if now_playing:
            embed.add_field(name='Now Playing:', value=f'{now_playing.title}\n{now_playing_time}', inline=True)
            thumbnail = await wavelink.YouTubeTrack.fetch_thumbnail(now_playing)
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
        else:
            embed.add_field(name='Nothing is playing right now', value=':(', inline=True)
        embed.add_field(name='', value='▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁', inline=False)
        embed.set_footer(text='2137', icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
        return embed

    async def replace_message(self, voice_client: WavelinkPlayer):
        """
        Removes last message and sends new one to keep it on the bottom of the chat\n
        """
        embed = await self.calculate_embed(voice_client)
        self.update_view_state(voice_client)
        self._replace_message(embed, loop=self.bot.loop)

    @run_threadsafe
    async def _replace_message(self, embed: discord.Embed, *, loop: asyncio.AbstractEventLoop):
        """
        internal function for replacing handle
        runs as threadsafe to prevent race condition
        * run it without await - it is not a coroutine
        """
        if self.message_handle:
            await self.message_handle.delete()
        self.message_handle = await self.text_channel.send(content=None, embed=embed, view=self)
