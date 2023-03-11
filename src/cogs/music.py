import discord
from utils.YT_source import YTDLSource
from discord.ext import commands
from discord import app_commands
import datetime

class Music(commands.Cog):
    """
    Class for music commands.
    """
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.queue = []


    def _play(self,client):
        if len(self.queue) > 0:
            self.queue.pop(0)
            client.voice_client.play(self.queue[0], after=lambda e: self._play(client))

    @app_commands.command(name="yt")
    async def yt_play(self, interaction: discord.Interaction, url: str):
        """Plays from a url (almost anything youtube_dl supports)"""
        guild = interaction.guild
        channel = interaction.user.voice.channel

        if not discord.utils.get(self.bot.voice_clients, guild=guild):
            await channel.connect()

        player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
        self.queue.append(player)

        if not guild.voice_client.is_playing():
            guild.voice_client.play(self.queue[0], after=lambda e: self._play(guild))
            guild.voice_client.is_playing()

        current_queue = '\n-'.join(str(element.title) for element in self.queue)
        embed = discord.Embed(title='The Boi',
                              color=0x00ff00,
                              timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name='queue', value=current_queue)
        embed.add_field(name='Now Playing', value=f'{self.queue[0].title}')
        embed.set_footer(text='2137',
                        icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
        await interaction.response.send_message(embed=embed)
