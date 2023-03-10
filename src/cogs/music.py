import discord
from utils.YT_source import YTDLSource
from discord.ext import commands
from discord import app_commands
import datetime

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    @commands.command()
    async def play(self, ctx, *, query):
        """Plays a file from the local filesystem"""

        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
        ctx.voice_client.play(source, after=lambda e: print(f'Player error: {e}') if e else None)

        await ctx.send(f'Now playing: {query}')

    @app_commands.command(name="yt")
    async def yt_play(self, interaction: discord.Interaction, url: str):
        """Plays from a url (almost anything youtube_dl supports)"""
        guild = interaction.guild
        if interaction.user.voice.channel:
            channel = interaction.user.voice.channel
            await channel.connect()
        player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
        guild.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
        embed = discord.Embed(title='Boiiiii', color=0x00ff00, timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name='Now Playing', value=f'{player.title}')
        embed.set_footer(text='2137', icon_url='https://media.tenor.com/mc3OyxhLazUAAAAM/doggo-doge.gif')
        await interaction.response.send_message(embed=embed)


    @commands.command()
    async def stream(self, ctx, *, url):
        """Streams from a url (same as yt, but doesn't predownload)"""

        async with ctx.typing():
            player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)

        await ctx.send(f'Now playing: {player.title}')

    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send(f"Changed volume to {volume}%")

    @commands.command()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""

        await ctx.voice_client.disconnect()

    @play.before_invoke
    #@yt.before_invoke
    @stream.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()
