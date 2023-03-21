from __future__ import annotations
from typing import TYPE_CHECKING
import re
import logging
import datetime
import asyncio
from io import BytesIO
import discord
import yt_dlp
import wavelink
from discord.ext import commands
from discord import app_commands
from utils.endpoints import Endpoints

if TYPE_CHECKING:
  from main import BoiBot


class AudioPlayer(commands.Cog):
  """
  Class for music commands.
  self.views is dictionary that holds handle to a message with audio controls view {guild_id:view},
  """
  def __init__(self, bot: BoiBot) -> None:
    self.bot:BoiBot = bot
    self.views:dict[int, PlayerControlView] = {}


  @commands.cooldown(rate=1, per=1)
  @commands.guild_only()
  @app_commands.command(name="play")
  async def play(self, interaction: discord.Interaction, search: str):
    """
    For soundboard type audio ID from list
    For youtube type url or search phrase
    """
    await interaction.response.send_message(f"Looking for {search}...")

    guild_id = interaction.guild_id
    if interaction.user.voice:
      voice_channel = interaction.user.voice.channel
    else:
      await interaction.edit_original_response(content="You're not in voice channel")
      return

    # Connect to vc or change vc to the one caller is in
    bot_vc: wavelink.Player = interaction.guild.voice_client
    if not bot_vc:
      bot_vc = await voice_channel.connect(cls=wavelink.Player)
    elif bot_vc.channel != voice_channel:
      await bot_vc.move_to(voice_channel)

    try:
      search_result = await self._add_to_queue(search, bot_vc)
      if not search_result:
        await interaction.edit_original_response(content=f"Couldn't find \"{search}\".")
        return

      await interaction.edit_original_response(content=f"Found \"{search_result.title}\".")
      if not bot_vc.is_playing():
        first_in_queue = await bot_vc.queue.get_wait()
        await bot_vc.play(first_in_queue)

      # Get/create view with audio controls
      view = self.views.get(guild_id)
      if not view or not view.active:
        view = PlayerControlView(self.bot, guild_id, interaction.channel)
        self.views[guild_id] = view
      await view._send_embed(bot_vc)

    # Catch errors
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
      await interaction.edit_original_response(content=f"\"{search}\" not available.")


  @commands.cooldown(rate=1, per=1)
  @commands.guild_only()
  @app_commands.command(name='disconnect')
  async def disconnect(self, interaction: discord.Interaction) -> None:
    """
    Simple disconnect command.
    This command assumes there is a currently connected Player.
    """
    bot_vc: wavelink.Player = interaction.guild.voice_client
    await bot_vc.disconnect()
    await interaction.response.send_message(content='Bot disconnected')

  @commands.guild_only()
  @app_commands.command(name="soundboard")
  async def list_soundboard(self, interaction: discord.Interaction):
    """
    Lists all audio files uploaded to soundboard
    """
    await interaction.response.send_message("Preparing list...")
    guild_soundboard = Endpoints.get_soundboard(interaction.guild_id)
    message_content = "SOUNDBOARD\n"
    i = 0
    for entry in guild_soundboard:
      i+=1
      message_content += f'{i}. {entry}\n'

    file = discord.File(fp=BytesIO(message_content.encode("utf8")), filename="soundboard.cpp")
    await interaction.edit_original_response(content='', attachments=[file])

  @commands.guild_only()
  @app_commands.command(name="volume")
  async def set_volume(self, interaction: discord.Interaction, value: int):
    """
    Set volume. Range: 0-100
    """
    if value < 0 or value > 100:
      await interaction.response.send_message("Value must be between 0 and 100")
      return

    bot_vc: wavelink.Player = interaction.guild.voice_client
    if bot_vc:
      bot_vc.volume = value
      await interaction.response.send_message(f"Value set to {value}")
    else:
      await interaction.response.send_message("Bot must be in voice channel")

  @commands.cooldown(rate=1, per=1)
  @commands.guild_only()
  @app_commands.command(name="upload")
  async def upload_audio(self, interaction: discord.Interaction, mp3_file: discord.Attachment):
    """
    Upload audio file to soundboard
    """
    await interaction.response.send_message("Processing file...")

    if not mp3_file.filename.endswith(".mp3"):
      await interaction.edit_original_response(content='Audio files must have .mp3 format')
      return

    mp3_file_bytes = await mp3_file.read()
    result = Endpoints.upload_audio(interaction.guild_id, mp3_file.filename, mp3_file_bytes)
    await interaction.edit_original_response(content=result)

  @commands.Cog.listener()
  async def on_wavelink_track_end(self, payload: wavelink.TrackEventPayload) -> None:
    """
    Callback function used for players to play next audio source in queue
    """
    guild_id = payload.player.guild.id
    bot_vc = payload.player
    view = self.views.get(guild_id)
    guild_queue = bot_vc.queue
    if guild_queue.count > 0:
      # Play next in queue
      next_audio_track = await guild_queue.get_wait()
      await bot_vc.play(next_audio_track)
      # Update embed
      await view._send_embed(bot_vc)
    else:
      if view:
        view._remove_embed()
        self.views.pop(guild_id)

  async def _add_to_queue(self, search:str, bot_vc:wavelink.Player) -> wavelink.Playable | None:
    """
    Creates audio tracks and adds it to queue
    """
    guild_id = bot_vc.guild.id
    found_playlist = re.search(r"^.*youtu.be\/|list=([^#\&\?]*).*", search)
    # Check if user wants to play audio from Youtube Playlist...
    if found_playlist:
      playlist = await wavelink.YouTubePlaylist.search(found_playlist.groups()[0], return_first=True)
      for track in playlist.tracks:
        await bot_vc.queue.put_wait(track)
      audio_track = playlist.tracks[0]
    # ...or soundboard...
    elif search.isnumeric():
      sound_id = int(search)
      guild_soundboard = Endpoints.get_soundboard(guild_id)
      if not guild_soundboard or sound_id > len(guild_soundboard):
        return None

      file_name = guild_soundboard[int(search) - 1]
      file_path = f'sounds/{str(guild_id)}/{file_name}'
      audio_track = await wavelink.GenericTrack.search(file_path, return_first=True)
      await bot_vc.queue.put_wait(audio_track)
    # ...or Youtube track.
    else:
      audio_track = await wavelink.YouTubeTrack.search(search, return_first=True)
      await bot_vc.queue.put_wait(audio_track)
    return audio_track


class PlayerControlView(discord.ui.View):
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


  @discord.ui.button(label='▶▶ Skip', style=discord.ButtonStyle.blurple)
  async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    """
    Skip track on button press
    """
    bot_vc:wavelink.Player = interaction.guild.voice_client
    user_vc = interaction.user.voice
    if not (bot_vc and user_vc and bot_vc.channel.id == user_vc.channel.id):
      await interaction.response.send_message("You cannot control the bot (check voice channel)",
                                              delete_after=3, ephemeral=True)
      return

    if bot_vc.is_playing():
      await bot_vc.stop()
      await interaction.response.defer()
    else:
      await interaction.response.send_message("Nothing is playing right now",
                                              delete_after=3, ephemeral=True)

  @discord.ui.button(label='|| Pause', style=discord.ButtonStyle.blurple)
  async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    """
    Pause/resume the player on button press
    """
    bot_vc:wavelink.Player = interaction.guild.voice_client
    user_vc = interaction.user.voice
    if not (bot_vc and user_vc and bot_vc.channel.id == user_vc.channel.id):
      await interaction.response.send_message("You cannot control the bot (check voice channel)",
                                              delete_after=3, ephemeral=True)
      return

    if not bot_vc.is_paused():
      await bot_vc.pause()
      button.label = '▶ Resume'
    else:
      await bot_vc.resume()
      button.label = '|| Pause'
    await interaction.response.edit_message(view=self)

  @discord.ui.button(label='▮ Stop', style=discord.ButtonStyle.red)
  async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    """
    Stop track on button press
    """
    bot_vc:wavelink.Player = interaction.guild.voice_client
    user_vc = interaction.user.voice
    if not (bot_vc and user_vc and bot_vc.channel.id == user_vc.channel.id):
      await interaction.response.send_message("You cannot control the bot (check voice channel)",
                                              delete_after=3, ephemeral=True)
      return

    if bot_vc.is_playing():
      bot_vc.queue.clear()
      await bot_vc.stop()
      await interaction.response.defer()
      self._remove_embed()
      self.stop()
      self.active = False
    else:
      await interaction.response.send_message("Nothing is playing right now",
                                              delete_after=3, ephemeral=True)

  def _remove_embed(self):
    """
    Removes embed with audio player informations
    """
    if self.embed_handle:
      coro = self.embed_handle.delete()
      self.stop()
      self.clear_items()
      asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

  async def _send_embed(self, bot_vc:wavelink.Player):
    """
    Removes last message and sends new one to keep it on the bottom of the chat
    """
    if self.embed_handle:
      await self.embed_handle.delete()

    # Calculate queue time length
    now_playing = bot_vc.current
    total_secods = 0
    for i in range(bot_vc.queue.count):
      total_secods += bot_vc.queue[i].length / 1000
    mins = divmod(total_secods, 60)[0]
    hour, mins = divmod(mins, 60)
    queue_time = f'⌛ {int(hour):02d} hr {int(mins):02d} min'
    mins, secs = divmod(now_playing.length / 1000, 60)
    now_playing_time = f'⌛ {int(mins):02d} min {int(secs):02d} s'

    # Prepare queue list
    queue_preview = ''
    if bot_vc.queue.count > 10:
      for i in range(10):
        queue_preview += f"{i+1}. {str(bot_vc.queue[i].title)}\n"
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
      embed.add_field(name='Queue', value=queue_preview, inline=False)
    embed.add_field(name='Now Playing', value=f'{now_playing.title}\n{now_playing_time}', inline=True)
    embed.add_field(name='', value='▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁', inline=False)
    embed.set_footer(text='2137',
                    icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
    thumbnail = await wavelink.YouTubeTrack.fetch_thumbnail(now_playing)
    if thumbnail:
      embed.set_thumbnail(url=thumbnail)

    self.embed_handle = await self.text_channel.send(content=None, embed=embed, view=self)
