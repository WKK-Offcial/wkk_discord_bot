import datetime
import asyncio
import discord
import yt_dlp
from discord.ext import commands
from discord import app_commands
from utils.YT_source import YTDLSource



class Music(commands.Cog):
  """
  Class for music commands.
  self.queue is a FIFO queue dictionary {guild_id:list_of_audio_sources},
  self.embed_handles is dictionary that holds handle to a message with player embed {guild_id:message_handle},
  """
  def __init__(self, bot: commands.Bot) -> None:
    self.bot = bot
    self.queue = {}
    self.embed_handles = {}

  def _prepare_embed(self, queue):
    """Creates and returns embed based on guild's queue content"""
    current_queue = ''.join(f"{str(element.title)}\n" for element in queue[1:])
    embed = discord.Embed(title='The Boi',
                          color=0x00ff00,
                          timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name='queue', value=current_queue)
    embed.add_field(name='Now Playing', value=f'{queue[0].title}')
    embed.set_footer(text='2137',
                    icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
    return embed


  async def _manage_embeds(self, guild_id, text_channel, queue):
    """Removes last message and sends new one to keep it on the bottom of the chat"""
    current_embed = self.embed_handles.get(guild_id)
    if current_embed is not None:
      await current_embed.delete()
    new_embed = self._prepare_embed(queue)
    self.embed_handles[guild_id] = await text_channel.send(content=None, embed=new_embed)


  def _play_next(self, interaction):
    """Callback function used for players to play next audio source in queue"""
    guild_queue = self.queue[interaction.guild_id]
    guild_queue.pop(0)
    if len(guild_queue) > 0:
      # Update embed
      coro = self._manage_embeds(interaction.guild_id, interaction.channel, guild_queue)
      asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

      # Play next in queue
      next_audio_source = guild_queue[0]
      interaction.guild.voice_client.play(next_audio_source, after=lambda e: self._play_next(interaction))
    else:
      # Remove player embed
      current_embed = self.embed_handles.get(interaction.guild_id)
      if current_embed is not None:
        coro = current_embed.delete()
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

  @app_commands.command(name="yt")
  async def yt_play(self, interaction: discord.Interaction, url: str):
    """Plays from a url (almost anything youtube_dl supports)"""
    await interaction.response.send_message(f"Looking for {url}...")
    guild = interaction.guild
    channel = interaction.user.voice.channel

    if not discord.utils.get(self.bot.voice_clients, guild=guild):
      await channel.connect()

    try:
      audio_source = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
      guild_queue = self.queue.get(guild.id, [])
      guild_queue.append(audio_source)
      self.queue[guild.id] = guild_queue

      if not guild.voice_client.is_playing():
        interaction.guild.voice_client.play(audio_source, after=lambda e: self._play_next(interaction))
      await interaction.edit_original_response(content=f"Found \"{audio_source.title}\".")
      await self._manage_embeds(interaction.guild_id, interaction.channel, guild_queue)
    except TypeError:
      await interaction.edit_original_response(content="Request sent too fast!")
    except yt_dlp.utils.ExtractorError:
      await interaction.edit_original_response(content=f"\"{url}\" not available.")
