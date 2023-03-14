import datetime
import asyncio
import discord
import yt_dlp
from discord.ext import commands
from discord import app_commands
from utils.YT_source import YTDLSource



class AudioPlayer(commands.Cog):
  """
  Class for music commands.
  self.queue is a FIFO queue dictionary {guild_id:list_of_audio_sources},
  self.embed_handles is dictionary that holds handle to a message with player embed {guild_id:message_handle},
  """
  def __init__(self, bot: commands.Bot) -> None:
    self.bot = bot
    self.queue = {}
    self.embed_handles = {}

  def _add_to_queue(self, guild_id:int, audio_source:YTDLSource):
    guild_queue = self.queue.get(guild_id, [])
    guild_queue.append(audio_source)
    self.queue[guild_id] = guild_queue
    return guild_queue


  def _create_embed(self, guild_queue:list):
    """Creates and returns embed based on guild's queue content"""
    now_playing = guild_queue[0]
    current_queue = ''.join(f"{str(element.title)}\n" for element in guild_queue[1:])
    embed = discord.Embed(title='The Boi',
                          color=0x00ff00,
                          timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name='queue', value=current_queue)
    embed.add_field(name='Now Playing', value=f'{now_playing.title}')
    embed.set_footer(text='2137',
                    icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
    return embed

  def _remove_embed(self, guild_id:int):
    current_embed = self.embed_handles.pop(guild_id, None)
    if current_embed:
      coro = current_embed.delete()
      asyncio.run_coroutine_threadsafe(coro, self.bot.loop)


  async def _pull_down_embed(self, guild_id:int, text_channel:discord.TextChannel, guild_queue:list):
    """Removes last message and sends new one to keep it on the bottom of the chat"""
    current_embed = self.embed_handles.get(guild_id)
    if current_embed:
      await current_embed.delete()
    new_embed = self._create_embed(guild_queue)
    self.embed_handles[guild_id] = await text_channel.send(content=None, embed=new_embed)


  def _play_next(self, interaction:discord.Interaction):
    """Callback function used for players to play next audio source in queue"""
    guild_queue = self.queue.get(interaction.guild_id)
    if guild_queue:
      guild_queue.pop(0)

    if guild_queue and len(guild_queue) > 0:
      # Update embed
      coro = self._pull_down_embed(interaction.guild_id, interaction.channel, guild_queue)
      asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

      # Play next in queue
      next_audio_source = guild_queue[0]
      interaction.guild.voice_client.play(next_audio_source, after=lambda e: self._play_next(interaction))
    else:
      self._remove_embed(interaction.guild_id)


  @app_commands.command(name="yt")
  async def play_yt(self, interaction: discord.Interaction, search_phrase: str):
    """Plays from a url (almost anything youtube_dl supports)"""
    await interaction.response.send_message(f"Looking for {search_phrase}...")
    guild = interaction.guild
    voice_channel = interaction.user.voice.channel
    text_channel = interaction.channel

    if not discord.utils.get(self.bot.voice_clients, guild=guild):
      await voice_channel.connect()

    try:
      audio_source = await YTDLSource.from_url(search_phrase, loop=self.bot.loop, stream=True)
      guild_queue = self._add_to_queue(guild.id, audio_source)

      if not guild.voice_client.is_playing():
        guild.voice_client.play(audio_source, after=lambda e: self._play_next(interaction))

      await interaction.edit_original_response(content=f"Found \"{audio_source.title}\".")
      await self._pull_down_embed(guild.id, text_channel, guild_queue)

    except TypeError:
      await interaction.edit_original_response(content="Request sent too fast!")
    except yt_dlp.utils.ExtractorError:
      await interaction.edit_original_response(content=f"\"{search_phrase}\" not available.")

  @app_commands.command(name="skip")
  async def skip_audio(self, interaction: discord.Interaction):
    """
    Skip currently played audio
    """
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
      voice_client.stop()
      await interaction.response.send_message("Skipped audio")
    else:
      await interaction.response.send_message("Nothing is playing right now")


  @app_commands.command(name="stop")
  async def stop_player(self, interaction: discord.Interaction):
    """
    Skip currently played audio
    """
    guild = interaction.guild

    self.queue.pop(guild.id, None)
    if  guild.voice_client and guild.voice_client.is_playing():
      guild.voice_client.stop()
      await guild.voice_client.disconnect()
      await interaction.response.send_message("Stopped player")
    else:
      await interaction.response.send_message("Nothing is playing right now")

    self._remove_embed(guild.id)
