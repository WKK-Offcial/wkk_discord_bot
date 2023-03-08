import asyncio
import discord
import os
from discord.ext import commands
from cogs.music import Music
from dotenv import load_dotenv

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("/"),
    description='The Boi is back',
    intents=intents,
)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')


async def main():
    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start(os.getenv('BOT_TOKEN'))


asyncio.run(main())
