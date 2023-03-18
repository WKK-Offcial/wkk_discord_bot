from __future__ import annotations
from typing import TYPE_CHECKING
import os
import logging
import datetime
import asyncio
from io import BytesIO
import discord
import yt_dlp
import wavelink
from discord.ext import commands
from discord import app_commands

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


  @commands.Cog.listener()
  async def on_wavelink_track_end(self, payload: wavelink.TrackEventPayload) -> None:
    """
    Callback function used for players to play next audio source in queue
    """
    guild_id = payload.player.guild.id
    voice_client = payload.player
    view = self.views.get(guild_id)
    guild_queue = voice_client.queue
    if guild_queue.count > 0:
      # Play next in queue
      next_audio_source = await guild_queue.get_wait()
      await voice_client.play(next_audio_source)
      # Update embed
      await view._send_embed(voice_client)
    else:
      if view:
        view._remove_embed()
        self.views.pop(guild_id)


  @app_commands.command(name="play")
  async def play(self, interaction: discord.Interaction, input_text: str):
    """
    For soundboard type audio ID from list\nFor youtube type url or search phrase
    """
    await interaction.response.send_message(f"Looking for {input_text}...")
    guild = interaction.guild
    if interaction.user.voice:
      voice_channel = interaction.user.voice.channel
    else:
      await interaction.edit_original_response(content="You're not in voice channel")
      return

    # Get voice client
    if not interaction.guild.voice_client:
      voice_client: wavelink.Player = await voice_channel.connect(cls=wavelink.Player)
    else:
      voice_client: wavelink.Player = interaction.guild.voice_client

    try:
      # Check if user wants to play audio from soundboard or from youtube
      if input_text.isnumeric():
        guild_soundboard = self.bot.get_soundboard(guild.id)
        file_name = guild_soundboard[int(input_text) - 1]
        file_path = os.path.abspath(f'cache/soundboards/{str(guild.id)}/{file_name}')
        audio_source = await wavelink.GenericTrack.search(file_path, return_first=True)
      else:
        audio_source = await wavelink.YouTubeTrack.search(input_text, return_first=True)

      # Add to queue and start playback if not yet playing
      if not voice_client.is_playing():
        await voice_client.play(audio_source)
      else:
        await voice_client.queue.put_wait(audio_source)

      await interaction.edit_original_response(content=f"Found \"{audio_source.title}\".")

      # Get/create view with audio controls
      view = self.views.get(guild.id)
      if not view or not view.active:
        view = AudioControls(self.bot, guild.id, interaction.channel)
        self.views[guild.id] = view
      await view._send_embed(voice_client)

    except SyntaxError:
      await interaction.edit_original_response(content='No argument passed!')
      logging.error(SyntaxError.msg)
    except IndexError:
      await interaction.edit_original_response(content='Index out of range!')
      logging.error(IndexError)
    except TypeError:
      await interaction.edit_original_response(content="Type error!")
      logging.error(TypeError)
    except yt_dlp.utils.ExtractorError:
      logging.error(yt_dlp.utils.ExtractorError.msg)
      await interaction.edit_original_response(content=f"\"{input_text}\" not available.")


  @app_commands.command(name='disconnect')
  async def disconnect(self, interaction: discord.Interaction) -> None:
    """
    Simple disconnect command.
    This command assumes there is a currently connected Player.
    """
    voice_client: wavelink.Player = interaction.guild.voice_client
    await voice_client.disconnect()

  @app_commands.command(name="soundboard")
  async def list_soundboard(self, interaction: discord.Interaction):
    """
    Lists all audio files uploaded to soundboard
    """
    await interaction.response.send_message("Preparing list...")
    guild_soundboard = self.bot.get_soundboard(interaction.guild_id)
    message_content = "SOUNDBOARD\n"
    i = 0
    for entry in guild_soundboard:
      i+=1
      message_content += f'{i}. {entry}\n'

    file = discord.File(fp=BytesIO(message_content.encode("utf8")), filename="soundboard.cpp")
    await interaction.edit_original_response(content='', attachments=[file])

  @app_commands.command(name="upload")
  async def upload_audio(self, interaction: discord.Interaction, mp3_file: discord.Attachment):
    """
    Upload audio file to soundboard
    """
    await interaction.response.send_message("Processing file...")

    if not mp3_file.filename.endswith(".mp3"):
      await interaction.edit_original_response(content='Audio files must have .mp3 format')
      return

    save_location = f"./cache/soundboards/{interaction.guild_id}/{mp3_file.filename}"
    await mp3_file.save(save_location)
    self.bot.dropbox.upload_file(save_location, interaction.guild_id)
    self.bot.add_to_soundboard(interaction.guild_id, mp3_file.filename)
    await interaction.edit_original_response(content=f'Successfully uploaded {mp3_file.filename}')


class AudioControls(discord.ui.View):
  """
  View class for controlling audio player through view
  """
  def __init__(self, bot: BoiBot, guild_id:int, text_channel:discord.TextChannel):
    super().__init__(timeout=None)
    self.bot:BoiBot = bot
    self.guild_id:int = guild_id
    self.text_channel:discord.TextChannel = text_channel
    self.embed_handle:discord.Message = None
    self.active = True

  def _remove_embed(self):
    """
    Removes embed with audio player informations
    """
    if self.embed_handle:
      coro = self.embed_handle.delete()
      self.stop()
      self.clear_items()
      asyncio.run_coroutine_threadsafe(coro, self.bot.loop)


  async def _send_embed(self, voice_client:wavelink.Player):
    """
    Removes last message and sends new one to keep it on the bottom of the chat
    """
    if self.embed_handle:
      await self.embed_handle.delete()

    # Create new embed
    now_playing = voice_client.current
    current_queue = ''.join(f"{str(element.title)}\n" for element in voice_client.queue)
    embed = discord.Embed(title='The Boi',
                          color=0x00ff00,
                          timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name='Queue', value=current_queue, inline=False)
    embed.add_field(name='Now Playing', value=f'{now_playing.title}', inline=True)
    embed.set_footer(text='2137',
                    icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
    if now_playing.thumbnail:
      embed.set_thumbnail(url=now_playing.thumbnail)

    self.embed_handle = await self.text_channel.send(content=None, embed=embed, view=self)

  @discord.ui.button(label='Skip', style=discord.ButtonStyle.green)
  async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    """
    When skip button is pressed skip current audio
    """
    button.is_persistent() # Useless - pylint about button not being used otherwise
    voice_client:wavelink.Player = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
      await voice_client.stop()
      await interaction.response.defer()
    else:
      await interaction.response.send_message("Nothing is playing right now", delete_after=1)


  @discord.ui.button(label='Stop', style=discord.ButtonStyle.red)
  async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    """
    When stop button is pressed stop audio playback and clear queue
    """
    button.is_persistent() # Useless - pylint about button not being used otherwise
    voice_client:wavelink.Player = interaction.guild.voice_client

    if  voice_client and voice_client.is_playing():
      voice_client.queue.clear()
      await voice_client.stop()
      await interaction.response.defer()
    else:
      await interaction.response.send_message("Nothing is playing right now", delete_after=1)

    self._remove_embed()
    self.stop()
    self.active = False

  @discord.ui.button(label='Vol+', style=discord.ButtonStyle.gray)
  async def volume_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    """
    Volume up by 10%
    """
    button.is_persistent() # Useless - pylint about button not being used otherwise
    voice_client:wavelink.Player = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
      new_volume = min(voice_client.volume + 20, 100)
      await voice_client.set_volume(new_volume)
      if new_volume == 100:
        button.disabled = True
      self.volume_down_button.disabled = False
      await interaction.response.edit_message(view=self)
    else:
      await interaction.response.defer()


  @discord.ui.button(label='Vol-', style=discord.ButtonStyle.gray)
  async def volume_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    """
    Volume down by 10%
    """
    voice_client:wavelink.Player = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
      new_volume = max(voice_client.volume - 20, 0)
      await voice_client.set_volume(new_volume)
      if new_volume == 0:
        button.disabled = True
      self.volume_up_button.disabled = False
      await interaction.response.edit_message(view=self)
    else:
      await interaction.response.defer()
