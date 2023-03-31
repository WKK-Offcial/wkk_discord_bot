from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING

import discord
import wavelink

from utils.decorators import (
    is_playing_check,
    run_threadsafe,
    user_bot_in_same_channel_check,
)
from utils.wavelink_player import WavelinkPlayer

if TYPE_CHECKING:
    from main import DiscordBot


class PlayerControlView(discord.ui.View):
    """
    View class for controlling audio player through view
    """

    def __init__(self, bot: DiscordBot, text_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.bot: DiscordBot = bot
        self.text_channel: discord.TextChannel = text_channel
        self.message_handle: discord.Message = None

    @discord.ui.button(label='◀◀ Prev', style=discord.ButtonStyle.blurple)
    @user_bot_in_same_channel_check
    async def undo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Undo a song skip.
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await interaction.response.defer()
        await voice_client.previous()

        # last_track = await voice_client.history.get_wait()
        # track_start_time = voice_client.track_start_times.get(last_track.title, 0)

        # if voice_client.is_playing() or voice_client.is_paused():
        #     current_track = voice_client.current
        #     voice_client.queue.put_at_front(current_track)
        #     await voice_client.play(last_track, start=track_start_time)
        # else:
        #     # Update embed since it won't be updated by on_track_end event
        #     await voice_client.play(last_track, start=track_start_time)
        #     if voice_client.history.count == 0:
        #         self.undo_button.disabled = True
        #     await self.update_message(voice_client)

    @discord.ui.button(label='❚❚ Pause', style=discord.ButtonStyle.blurple)
    @user_bot_in_same_channel_check
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Pause/resume the player on button press
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await voice_client.toggle_pause()
        self.update_buttons(voice_client)
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label='▶▶ Skip', style=discord.ButtonStyle.blurple)
    @user_bot_in_same_channel_check
    @is_playing_check
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Skip track on button press
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await interaction.response.defer()
        await voice_client.next()

    @discord.ui.button(label='▮ Stop', style=discord.ButtonStyle.red)
    @user_bot_in_same_channel_check
    @is_playing_check
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Stop track on button press
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await voice_client.stop_all()
        self.update_buttons(voice_client)
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label='ඞ', style=discord.ButtonStyle.grey)
    @user_bot_in_same_channel_check
    @is_playing_check
    async def filter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        fourth density
        """
        voice_client: WavelinkPlayer = interaction.guild.voice_client
        await voice_client.toggle_cursed_filter()
        self.update_buttons(voice_client)
        await interaction.response.edit_message(view=self)

    def update_buttons(self, voice_client: WavelinkPlayer):
        """
        calculates state of buttons
        """
        # fmt: off
        self.undo_button.disabled = (
            len(voice_client.queue.history) <= 1 and voice_client.current) or (
            len(voice_client.queue.history) == 1 and not voice_client.current
        )  # because current song is also in this queue
        # fmt: on
        self.pause_button.disabled = not voice_client.current
        self.pause_button.label = '▶ Resume' if voice_client.is_paused() else '❚❚ Pause'
        self.skip_button.disabled = not voice_client.current
        self.stop_button.disabled = not voice_client.current
        self.filter_button.disabled = False
        self.filter_button.label = 'ඞ' if not voice_client.filter else ''
        self.filter_button.emoji = (
            discord.PartialEmoji.from_str('<a:amogus:1088546951949209620>') if voice_client.filter else None
        )

    def remove_view(self):
        """
        Removes embed with audio player information
        """
        if self.message_handle:
            coro = self.message_handle.delete()
            self.stop()
            self.clear_items()
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    async def update_message(self, voice_client: WavelinkPlayer):
        """
        Removes last message and sends new one to keep it on the bottom of the chat\n
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

        self.update_buttons(voice_client)
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
