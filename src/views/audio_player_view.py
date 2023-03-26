from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
import wavelink
from utils.wavelink_player import WavelinkPlayer
from utils.decorators import user_bot_in_same_channel_check, is_playing_check, button_cooldown

if TYPE_CHECKING:
    from main import BoiBot

class PlayerControlView(discord.ui.View):
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
        self.controls_enabled = True
        self._cooldown = commands.CooldownMapping.from_cooldown(rate = 1, per = 1, type = commands.BucketType.channel)

    @discord.ui.button(label='◀◀ Undo', style=discord.ButtonStyle.blurple)
    @user_bot_in_same_channel_check
    @button_cooldown
    async def undo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Undo a song skip.
        """
        bot_vc: WavelinkPlayer = interaction.guild.voice_client
        if bot_vc.history.count == 0:
            await interaction.response.send_message("Nothing was played before!",
                                                    delete_after=3, ephemeral=True)
            return

        await interaction.response.defer()
        last_track = await bot_vc.history.get_wait()
        track_start_time = bot_vc.track_start_times.get(last_track.title, 0)

        if bot_vc.is_playing() or bot_vc.is_paused():
            current_track = bot_vc.current
            bot_vc.queue.put_at_front(current_track)
            await bot_vc.play(last_track, start=track_start_time)
        else:
            # Update embed since it won't be updated by on_track_end event
            await bot_vc.play(last_track, start=track_start_time)
            self.enable_control_buttons()
            if bot_vc.history.count == 0:
                self.undo_button.disabled = True
            await self.send_embed(bot_vc)


    @discord.ui.button(label='❚❚ Pause', style=discord.ButtonStyle.blurple)
    @user_bot_in_same_channel_check
    @button_cooldown
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Pause/resume the player on button press
        """
        bot_vc: WavelinkPlayer = interaction.guild.voice_client

        if not bot_vc.is_paused():
            await bot_vc.pause()
            button.label = '▶ Resume'
        else:
            await bot_vc.resume()
            button.label = '❚❚ Pause'
        await interaction.response.edit_message(view=self)


    @discord.ui.button(label='▶▶ Skip', style=discord.ButtonStyle.blurple)
    @user_bot_in_same_channel_check
    @is_playing_check
    @button_cooldown
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Skip track on button press
        """
        bot_vc: WavelinkPlayer = interaction.guild.voice_client
        # Add to history
        current_track = bot_vc.current
        current_time = bot_vc.position
        bot_vc.track_start_times[current_track.title] = int(current_time)

        # Skip song
        await bot_vc.stop()
        await interaction.response.defer()


    @discord.ui.button(label='▮ Stop', style=discord.ButtonStyle.red)
    @user_bot_in_same_channel_check
    @is_playing_check
    @button_cooldown
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Stop track on button press
        """
        bot_vc: WavelinkPlayer = interaction.guild.voice_client
        # Add to history
        current_track = bot_vc.current
        current_time = bot_vc.position
        bot_vc.track_start_times[current_track.title] = int(current_time)

        # Clear player
        bot_vc.queue.clear()
        await bot_vc.stop()

        # Update view
        self.disable_control_buttons()
        await interaction.response.defer()


    @discord.ui.button(label='ඞ', style=discord.ButtonStyle.grey)
    @user_bot_in_same_channel_check
    @is_playing_check
    @button_cooldown
    async def filter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        fourth density
        """
        bot_vc: WavelinkPlayer = interaction.guild.voice_client
        user_vc = interaction.user.voice
        if not (bot_vc and user_vc and bot_vc.channel.id == user_vc.channel.id):
            await interaction.response.send_message("You cannot control the bot (check voice channel)",
                                                    delete_after=3, ephemeral=True)
            return

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


    def disable_control_buttons(self):
        """
        Disables all control buttons except undo button
        """
        self.skip_button.disabled = True
        self.stop_button.disabled = True
        self.pause_button.disabled = True
        self.filter_button.disabled = True
        self.filter_button.label = 'ඞ'
        self.filter_button.emoji = None
        self.controls_enabled = False

    def enable_control_buttons(self):
        """
        Enables all control buttons
        """
        self.skip_button.disabled = False
        self.stop_button.disabled = False
        self.pause_button.disabled = False
        self.filter_button.disabled = False
        self.undo_button.disabled = False
        self.controls_enabled = True

    def remove_view(self):
        """
        Removes embed with audio player information
        """
        if self.embed_handle:
            coro = self.embed_handle.delete()
            self.stop()
            self.clear_items()
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    async def send_embed(self, bot_vc: WavelinkPlayer):
        """
        Removes last message and sends new one to keep it on the bottom of the chat
        """
        if self.embed_handle:
            await self.embed_handle.delete()

        # Calculate queue time length
        total_seconds = 0
        for i in range(bot_vc.queue.count):
            total_seconds += bot_vc.queue[i].length / 1000
        minutes = divmod(total_seconds, 60)[0]
        hours, minutes = divmod(minutes, 60)
        queue_time = f'⌛ {int(hours):02d} hr {int(minutes):02d} min'

        now_playing = bot_vc.current
        if now_playing:
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
        embed = discord.Embed(title='The Boi',
                              color=0x00ff00,
                              timestamp=datetime.datetime.now(datetime.timezone.utc))
        if bot_vc.queue.count > 0:
            embed.add_field(name='Queue:', value=queue_preview, inline=False)
        if now_playing:
            embed.add_field(name='Now Playing:', value=f'{now_playing.title}\n{now_playing_time}', inline=True)
            thumbnail = await wavelink.YouTubeTrack.fetch_thumbnail(now_playing)
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
        else:
            embed.add_field(name='Nothing is playing right now', value=':(', inline=True)
        embed.add_field(name='', value='▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁', inline=False)
        embed.set_footer(text='2137',
                         icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')

        self.embed_handle = await self.text_channel.send(content=None, embed=embed, view=self)
