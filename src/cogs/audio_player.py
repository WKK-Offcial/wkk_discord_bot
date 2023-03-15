from __future__ import annotations
from typing import TYPE_CHECKING
import datetime
import asyncio
import discord
import yt_dlp
from discord.ext import commands
from discord import app_commands
from utils.youtube_audio import YoutubeSource

if TYPE_CHECKING:
  from main import BoiBot

class AudioPlayer(commands.Cog):
  """
  Class for music commands.
  self.views is dictionary that holds handle to a message with audio controls view {guild_id:view},
  """
  def __init__(self, bot: BoiBot) -> None:
    self.bot:BoiBot = bot
    self.views:dict[int, AudioControls] = {}

  def _add_to_queue(self, guild_id:int, audio_source:YoutubeSource):
    """
    Adds audio source to guild's queue
    """
    guild_queue = self.bot.get_queue(guild_id)
    guild_queue.append(audio_source)
    return guild_queue

  def _play_next(self, interaction:discord.Interaction):
    """
    Callback function used for players to play next audio source in queue
    """
    view = self.views.get(interaction.guild_id)
    guild_queue = self.bot.get_queue(interaction.guild_id)
    if guild_queue:
      guild_queue.pop(0)

    if guild_queue and len(guild_queue) > 0:
      # Update embed
      coro = view.pull_down_embed(interaction.channel, guild_queue)
      asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

      # Play next in queue
      next_audio_source = guild_queue[0]
      interaction.guild.voice_client.play(next_audio_source, after=lambda e: self._play_next(interaction))
    else:
      if view:
        view.remove_embed()
        self.views.pop(interaction.guild_id)


  @app_commands.command(name="yt")
  async def play_yt(self, interaction: discord.Interaction, search_phrase: str):
    """
    Plays from a url (almost anything youtube_dl supports)
    """
    await interaction.response.send_message(f"Looking for {search_phrase}...")
    guild = interaction.guild
    voice_channel = interaction.user.voice.channel
    text_channel = interaction.channel

    if not discord.utils.get(self.bot.voice_clients, guild=guild):
      await voice_channel.connect()

    try:
      audio_source = await YoutubeSource.from_url(search_phrase, loop=self.bot.loop, stream=True)
      guild_queue = self._add_to_queue(guild.id, audio_source)

      if not guild.voice_client.is_playing():
        guild.voice_client.play(audio_source, after=lambda e: self._play_next(interaction))

      await interaction.edit_original_response(content=f"Found \"{audio_source.title}\".")

      # Get/create view with audio controls
      view = self.views.get(guild.id)
      if not view or not view.active:
        view = AudioControls(self.bot, guild.id)
        self.views[guild.id] = view
      await view.pull_down_embed(text_channel, guild_queue)

    except TypeError:
      await interaction.edit_original_response(content="Request sent too fast!")
    except yt_dlp.utils.ExtractorError:
      await interaction.edit_original_response(content=f"\"{search_phrase}\" not available.")


class AudioControls(discord.ui.View):
  """
  View class for controlling audio player through view
  """
  def __init__(self, bot: BoiBot, guild_id:int):
    super().__init__()
    self.bot:BoiBot = bot
    self.guild_id:int = guild_id
    self.embed_handle:discord.Message = None
    self.active = True

  def remove_embed(self):
    """
    Removes embed with audio player informations
    """
    if self.embed_handle:
      coro = self.embed_handle.delete()
      self.stop()
      self.clear_items()
      asyncio.run_coroutine_threadsafe(coro, self.bot.loop)


  async def pull_down_embed(self, text_channel:discord.TextChannel, guild_queue:list):
    """
    Removes last message and sends new one to keep it on the bottom of the chat
    """
    if self.embed_handle:
      await self.embed_handle.delete()

    # Create new embed
    now_playing = guild_queue[0]
    current_queue = ''.join(f"{str(element.title)}\n" for element in guild_queue[1:])
    embed = discord.Embed(title='The Boi',
                          color=0x00ff00,
                          timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name='Queue', value=current_queue, inline=False)
    embed.add_field(name='Now Playing', value=f'{now_playing.title}', inline=True)
    embed.set_footer(text='2137',
                    icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
    embed.set_thumbnail(url=now_playing.thumbnail)

    self.embed_handle = await text_channel.send(content=None, embed=embed, view=self)

  @discord.ui.button(label='Skip', style=discord.ButtonStyle.green)
  async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    """
    When skip button is pressed skip current audio
    """
    button.is_persistent() # Useless - pylint about button not being used otherwise
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
      voice_client.stop()
      await interaction.response.send_message('Skipped audio', delete_after=1)
    else:
      await interaction.response.send_message("Nothing is playing right now", delete_after=1)


  @discord.ui.button(label='Stop', style=discord.ButtonStyle.red)
  async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    """
    When stop button is pressed stop audio playback and clear queue
    """
    button.is_persistent() # Useless - pylint about button not being used otherwise
    guild = interaction.guild

    self.bot.remove_queue(guild.id)
    if  guild.voice_client and guild.voice_client.is_playing():
      guild.voice_client.stop()
      await guild.voice_client.disconnect()
      await interaction.response.send_message('Stopped player', delete_after=1)
    else:
      await interaction.response.send_message("Nothing is playing right now", delete_after=1)

    self.remove_embed()
    self.stop()
    self.active = False

