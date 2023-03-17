import asyncio
import os
import yt_dlp
import discord

ytdl_format_options = {
  'format': 'bestaudio/best',
  'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
  'restrictfilenames': True,
  'noplaylist': True,
  'nocheckcertificate': True,
  'ignoreerrors': False,
  'logtostderr': False,
  'quiet': True,
  'no_warnings': True,
  'default_search': 'auto',
  'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
  'options': '-vn',
  'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


class AudioSource(discord.PCMVolumeTransformer):
  """
  Class responsible for obtaining stream source from youtube
  """
  def __init__(self, source:str, *, data:dict[str, ], volume=0.5):
    super().__init__(source, volume)

    self.title:str = data.get('title')
    self.url:str = data.get('url')
    self.thumbnail = data.get('thumbnail')

  @classmethod
  async def from_url(cls, url, *, loop=None, stream=False):
    """
    Get audio source from search phrase or direct video url
    """
    loop = loop or asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

    if 'entries' in data:
      # take first item from a playlist
      data = data['entries'][0]

    filename = data['url'] if stream else ytdl.prepare_filename(data)
    return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

  @classmethod
  def from_file(cls, file_name, *, loop=None):
    """
    Get audio source from search phrase or direct video url
    """
    loop = loop or asyncio.get_event_loop()
    data = {
      'title':os.path.basename(file_name),
      'url':'placeholder_url',
      'thumbnnail':'https://media.tenor.com/XWSuG5fuzL4AAAAC/pepe-peepo.gif',
    }
    return cls(discord.FFmpegPCMAudio(file_name), data=data)
