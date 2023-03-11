import discord
from utils.YT_source import YTDLSource
from discord.ext import commands
from discord import app_commands
import datetime
import asyncio

class Music(commands.Cog):
    """
    Class for music commands.
    """
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.queue = []


    def _play(self, interaction):
        if len(self.queue) > 0:
            # Play next in queue
            embed = self._prepare_embed()
            coro = interaction.channel.send(content=None, embed=embed)
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            play_next = self.queue.pop(0)
            interaction.guild.voice_client.play(play_next, after=lambda e: self._play(interaction))

    def _prepare_embed(self):
        current_queue = '\n-'.join(str(element.title) for element in self.queue)
        embed = discord.Embed(title='The Boi',
                              color=0x00ff00,
                              timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name='queue', value=current_queue)
        embed.add_field(name='Now Playing', value=f'{self.queue[0].title}')
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

        player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
        self.queue.append(player)

        if not guild.voice_client.is_playing():
            await interaction.edit_original_response(content=f"Now playing {url}.")
            self._play(interaction)
        else:
            await interaction.edit_original_response(content=f"Added {url} to queue.")
