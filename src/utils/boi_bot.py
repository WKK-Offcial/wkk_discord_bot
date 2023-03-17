import os
import bisect
from discord import Intents
from discord.ext import commands
from .dropbox_storage import DropboxManager

class BoiBot(commands.Bot):
  """
  Class inherited from Bot in order to add queues to it
  """
  def __init__(self):
    intents = Intents.default()
    intents.message_content = True
    super().__init__( command_prefix=commands.when_mentioned_or("/"),
                      description='The Boi is back',
                      intents=intents,)

    self._queues:dict[str, list] = {}
    self._soundboards:dict[str, list] = {}
    self.dropbox = DropboxManager()
    self.dropbox.download_all()

    # Load sounboards stored in cloud
    for root, dirs, files in os.walk('./cache/soundboards/'):
      for guild_id in dirs:
        self._soundboards[str(guild_id)] = []
      for file_name in files:
        guild_id = os.path.basename(root)
        self._soundboards[str(guild_id)].append(file_name)

  def get_queue(self, guild_id:int):
    """
    Returns queue for specified guild
    """
    queue = self._queues.get(str(guild_id))
    if not queue:
      self._queues[str(guild_id)] = queue = []
    return queue

  def remove_queue(self, guild_id:int):
    """
    Removes queue for specified guild
    """
    return self._queues.pop(str(guild_id), None)

  def get_soundboard(self, guild_id:int):
    """
    Returns queue for specified guild
    """
    soundboard = self._soundboards.get(str(guild_id))
    if not soundboard:
      self._soundboards[str(guild_id)] = soundboard = []
    return soundboard

  def add_to_soundboard(self, guild_id:int, file_name:str):
    """
    Adds audio file to sound list
    """
    bisect.insort(self._soundboards[str(guild_id)], file_name)