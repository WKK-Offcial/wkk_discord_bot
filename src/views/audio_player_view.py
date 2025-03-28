from __future__ import annotations

import asyncio
import datetime
from dataclasses import dataclass
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
    from main import DiscordBot


@dataclass
class QueueDisplay:
    """Configuration for queue display"""

    MAX_ITEMS = 25
    PLACEHOLDER = 'Nothing in current queue.'
    MAX_PREVIEW_ITEMS = 10


class AudioPlayerView(discord.ui.View):
    """View class for controlling audio player through Discord UI"""

    def __init__(self, bot: DiscordBot, text_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.bot = bot
        self.text_channel = text_channel
        self.message_handle: discord.Message | None = None
        self.queue_page = 0
        self._cooldown = commands.CooldownMapping.from_cooldown(rate=1, per=1, type=commands.BucketType.channel)
        self._setup_buttons()
        self._setup_queue_select()

    def __del__(self):
        if self.message_handle:
            coro = self.message_handle.delete()
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    def _setup_buttons(self):
        """Initialize button layouts and styles"""
        # Row 0: Playback controls
        self.previous_button = self._create_button(
            '◀◀ Prev', discord.ButtonStyle.blurple, self.previous_callback, row=0
        )
        self.pause_button = self._create_button('❚❚ Pause', discord.ButtonStyle.blurple, self.pause_callback, row=0)
        self.skip_button = self._create_button('▶▶ Skip', discord.ButtonStyle.blurple, self.skip_callback, row=0)
        self.stop_button = self._create_button('▮ Stop', discord.ButtonStyle.red, self.stop_callback, row=0)
        self.filter_button = self._create_button('ඞ', discord.ButtonStyle.grey, self.filter_callback, row=0)

        # Row 2: Navigation controls
        self.previous_page_button = self._create_button(
            '◀', discord.ButtonStyle.grey, self.previous_page_callback, row=2, disabled=True
        )
        self.next_page_button = self._create_button(
            '▶', discord.ButtonStyle.grey, self.next_page_callback, row=2, disabled=True
        )

    def _setup_queue_select(self):
        """Initialize queue selection dropdown"""
        self.queue_select = discord.ui.Select(
            options=[discord.SelectOption(label=QueueDisplay.PLACEHOLDER)],
            placeholder=QueueDisplay.PLACEHOLDER,
            max_values=1,
            min_values=1,
            disabled=True,
            row=1,
        )
        self.queue_select.callback = self.queue_select_callback
        self.add_item(self.queue_select)

    def _create_button(self, label: str, style: discord.ButtonStyle, callback, **kwargs) -> discord.ui.Button:
        """Create and configure a button with the given parameters"""
        button = discord.ui.Button(label=label, style=style, **kwargs)
        button.callback = callback
        self.add_item(button)
        return button

    async def remove_view(self):
        """Clean up resources and remove the view"""
        await self._delete_message_handle()
        self.stop()
        self.clear_items()

    async def send_embed(self):
        """Update the embed message with current player state"""
        embed = await self._create_embed()
        self._update_ui_state()

        await self._delete_message_handle()
        self.message_handle = await self.text_channel.send(embed=embed, view=self)

    def _format_duration(self, milliseconds: float) -> str:
        """Format milliseconds duration into human-readable string"""
        total_seconds = milliseconds / 1000
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f'⌛ {int(hours):02d} hr {int(minutes):02d} min'
        return f'⌛ {int(minutes):02d} min {int(seconds):02d} s'

    def _format_queue_preview(self, player: AudioPlayer) -> tuple[str, str]:
        """Format queue preview and duration"""
        if not player.queue:
            return '', ''

        total_duration = sum(track.length for track in player.queue)
        queue_duration = self._format_duration(total_duration)

        if len(player.queue) > QueueDisplay.MAX_PREVIEW_ITEMS:
            preview_tracks = [
                f"{i + 1}. {track.title}" for i, track in enumerate(player.queue[: QueueDisplay.MAX_PREVIEW_ITEMS])
            ]
            remaining = len(player.queue) - QueueDisplay.MAX_PREVIEW_ITEMS
            preview_tracks.append(f'... and {remaining} more.')
        else:
            preview_tracks = [f"{i + 1}. {track.title}" for i, track in enumerate(player.queue)]

        return '\n'.join(preview_tracks + [f'{queue_duration}']), queue_duration

    async def _create_embed(self) -> discord.Embed:
        """Create embed with current player information"""
        player = cast(AudioPlayer, self.text_channel.guild.voice_client)
        embed = discord.Embed(title='The Boi', color=0x00FF00, timestamp=datetime.datetime.now(datetime.timezone.utc))

        queue_preview, _ = self._format_queue_preview(player)
        if queue_preview:
            embed.add_field(name='Queue:', value=queue_preview, inline=False)

        if player.current:
            duration = self._format_duration(player.current.length)
            embed.add_field(name='Now Playing:', value=f'{player.current.title}\n{duration}', inline=True)
            if player.current.artwork:
                embed.set_thumbnail(url=player.current.artwork)
        else:
            embed.add_field(name='Nothing is playing right now', value=':(', inline=True)

        embed.add_field(name='', value='▁' * 15, inline=False)
        embed.set_footer(text='2137', icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
        return embed

    def _update_ui_state(self):
        """Update all UI elements based on current player state"""
        player = cast(AudioPlayer, self.text_channel.guild.voice_client)

        # Update button states
        self._update_playback_buttons(player)
        self._update_navigation_buttons(player)
        self._update_queue_select(player)

    def _update_playback_buttons(self, player: AudioPlayer):
        """Update state of playback control buttons"""
        self.previous_button.disabled = not len(player.queue.history) > 1
        self.pause_button.label = '▶ Resume' if player.paused else '❚❚ Pause'
        self.pause_button.disabled = not player.playing
        self.skip_button.disabled = not player.playing
        self.stop_button.disabled = not player.playing
        self.filter_button.disabled = not player.playing

        # Update filter button appearance
        dancing_emoji = discord.PartialEmoji.from_str('<a:catvibe:858756437705883648>')
        self.filter_button.label = '' if player.filters_applied else 'ඞ'
        self.filter_button.emoji = dancing_emoji if player.filters_applied else None

    def _update_navigation_buttons(self, player: AudioPlayer):
        """Update state of navigation buttons"""
        queue_len = len(player.queue)
        history_len = len(player.queue.history)

        max_pages = max(queue_len - 1, 0) // QueueDisplay.MAX_ITEMS
        min_pages = -(max(history_len - 1, 0) // QueueDisplay.MAX_ITEMS) - 1 if history_len else 0

        self.queue_page = min(max_pages, max(min_pages, self.queue_page))
        self.previous_page_button.disabled = self.queue_page <= min_pages
        self.next_page_button.disabled = self.queue_page >= max_pages

    def _update_queue_select(self, player: AudioPlayer):
        """Update queue selection dropdown"""
        if self.queue_page >= 0:
            self._update_current_queue_select(player)
        else:
            self._update_history_queue_select(player)

    def _update_current_queue_select(self, player: AudioPlayer):
        """Update dropdown for current queue"""
        start_idx = self.queue_page * QueueDisplay.MAX_ITEMS
        end_idx = (self.queue_page + 1) * QueueDisplay.MAX_ITEMS

        if not player.queue:
            self.queue_select.disabled = True
            self.queue_select.options = [discord.SelectOption(label=QueueDisplay.PLACEHOLDER)]
            self.queue_select.placeholder = QueueDisplay.PLACEHOLDER
            return

        self.queue_select.disabled = False
        self.queue_select.options = [
            discord.SelectOption(label=f'{i + 1}. {track.title}', value=str(i))
            for i, track in enumerate(player.queue[start_idx:end_idx])
        ]
        self.queue_select.placeholder = (
            f'Displaying: {start_idx + 1}-{min(end_idx, len(player.queue))} (current queue)'
        )

    def _update_history_queue_select(self, player: AudioPlayer):
        """Update dropdown for history queue"""
        history = list(player.queue.history)[::-1]
        start_idx = (-self.queue_page - 1) * QueueDisplay.MAX_ITEMS
        end_idx = -self.queue_page * QueueDisplay.MAX_ITEMS

        if not history:
            self.queue_select.disabled = True
            self.queue_select.options = [discord.SelectOption(label=QueueDisplay.PLACEHOLDER)]
            self.queue_select.placeholder = QueueDisplay.PLACEHOLDER
            return

        self.queue_select.disabled = False
        self.queue_select.options = [
            discord.SelectOption(label=f'{i + 1}. {track.title}', value=str(len(history) - 1 - i))
            for i, track in enumerate(history[start_idx:end_idx])
        ]
        self.queue_select.placeholder = f'Displaying: {start_idx + 1}-{min(end_idx, len(history))} (history queue)'

    async def _delete_message_handle(self):
        """Delete the message handle if it exists"""
        if self.message_handle:
            try:
                await self.message_handle.delete()
            except discord.NotFound:
                pass

    # Button Callbacks
    @user_bot_in_same_channel_check
    @button_cooldown
    async def previous_callback(self, interaction: discord.Interaction):
        """Play previous track"""
        player = cast(AudioPlayer, interaction.guild.voice_client)
        await player.play_previous_track()
        await interaction.response.defer()

    @user_bot_in_same_channel_check
    @button_cooldown
    async def pause_callback(self, interaction: discord.Interaction):
        """Toggle pause state"""
        player = cast(AudioPlayer, interaction.guild.voice_client)
        await player.pause(not player.paused)
        await interaction.response.defer()
        await self._update_embed()

    @user_bot_in_same_channel_check
    @is_playing_check
    @button_cooldown
    async def skip_callback(self, interaction: discord.Interaction):
        """Skip current track"""
        player = cast(AudioPlayer, interaction.guild.voice_client)
        await player.skip()
        await interaction.response.defer()

    @user_bot_in_same_channel_check
    @is_playing_check
    @button_cooldown
    async def stop_callback(self, interaction: discord.Interaction):
        """Stop playback and clear queue"""
        player = cast(AudioPlayer, interaction.guild.voice_client)
        player.queue.clear()
        await player.skip()
        await player.disable_filters()
        await interaction.response.defer()

    @user_bot_in_same_channel_check
    @is_playing_check
    async def filter_callback(self, interaction: discord.Interaction):
        """Toggle audio filters"""
        player = cast(AudioPlayer, interaction.guild.voice_client)
        await player.toggle_nightcore_filter()
        await interaction.response.defer()
        await self._update_embed()

    @user_bot_in_same_channel_check
    async def queue_select_callback(self, interaction: discord.Interaction):
        """Handle queue selection"""
        player = cast(AudioPlayer, interaction.guild.voice_client)
        index = int(self.queue_select.values[0])

        if self.queue_page >= 0:
            await player.play_track_from_queue(index)
        else:
            await player.play_track_from_history(index)

        await interaction.response.defer()

    @user_bot_in_same_channel_check
    async def previous_page_callback(self, interaction: discord.Interaction):
        """Show previous page of queue"""
        self.queue_page -= 1
        await interaction.response.defer()
        await self._update_embed()

    @user_bot_in_same_channel_check
    async def next_page_callback(self, interaction: discord.Interaction):
        """Show next page of queue"""
        self.queue_page += 1
        await interaction.response.defer()
        await self._update_embed()

    async def _update_embed(self):
        """Update existing embed message"""
        if not self.text_channel:
            return

        embed = await self._create_embed()
        self._update_ui_state()
        if self.message_handle:
            await self.message_handle.edit(view=self, embed=embed)
