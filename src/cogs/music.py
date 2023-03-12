import discord
from utils.YT_source import YTDLSource
from discord.ext import commands
from discord import app_commands
import datetime
import asyncio

class Music(commands.Cog):
  """
  Class for music commands. Queue is a dictionary {guild_id:queue}
  """
  def __init__(self, bot: commands.Bot) -> None:
    self.bot = bot
    self.queue = {}


  def _play(self, interaction):
    guild_queue = self.queue[interaction.guild_id]
    if len(guild_queue) > 0:
      # Send updated embed
      embed = self._prepare_embed(guild_queue)
      coro = interaction.channel.send(content=None, embed=embed)
      asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

      # Play next in queue
      next_audio_source = guild_queue.pop(0)
      interaction.guild.voice_client.play(next_audio_source, after=lambda e: self._play(interaction))

  def _prepare_embed(self, queue):
    current_queue = '\n-'.join(str(element.title) for element in queue)
    embed = discord.Embed(title='The Boi',
                          color=0x00ff00,
                          timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name='queue', value=current_queue)
    embed.add_field(name='Now Playing', value=f'{queue[0].title}')
    embed.set_footer(text='2137',
                    icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
    return embed

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
    except:
      await interaction.edit_original_response(content=f"Video not available.")
      return

    if not guild.voice_client.is_playing():
      await interaction.edit_original_response(content=f"Now playing {url}.")
      self._play(interaction)
    else:
      await interaction.edit_original_response(content=f"Added {url} to queue.")
