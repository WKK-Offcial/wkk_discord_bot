import asyncio
import functools
import inspect
from typing import cast
from audio_player import AudioPlayer

import discord
import wavelink


def bot_is_in_voice_channel_check(func):
    """
    Decorator used to check whether bot is in voice channel.
    Executes decorated function only if check passed
    """

    @functools.wraps(func)  # preserves signature of the function so it can be used in commands
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("Interaction is None")

        player = cast(AudioPlayer, interaction.guild.voice_client)
        if not player:
            await interaction.response.send_message("Bot not in voice channel", delete_after=3, ephemeral=True)
            return
        await func(*args, **kwargs)

    return decorator


def user_is_in_voice_channel_check(func):
    """
    Decorator used to check whether player is in voice channel.
    Executes decorated function only if check passed
    """

    @functools.wraps(func)  # preserves signature of the function so it can be used in commands
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("Interaction is None")

        voice_channel = interaction.user.voice
        if not voice_channel:
            await interaction.response.send_message(
                "You can't control the bot because you're not in a voice channel", delete_after=3, ephemeral=True
            )
            return
        await func(*args, **kwargs)

    return decorator


def user_bot_in_same_channel_check(func):
    """
    Decorator used to check whether player is able to use audio player controls.
    (Must be in the same voice channel)
    Executes decorated function only if check passed
    """

    @functools.wraps(func)  # preserves signature of the function so it can be used in commands
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("Interaction is None")

        player, voice_channel = cast(AudioPlayer, interaction.guild.voice_client), interaction.user.voice
        if not (player and voice_channel and player.channel.id == voice_channel.channel.id):
            msg = "You can't control the bot because you're not on the same voice channel"
            await interaction.response.send_message(msg, delete_after=3, ephemeral=True)
            return
        await func(*args, **kwargs)

    return decorator


def is_playing_check(func):
    """
    Decorator for checking if bot is playing something.
    Executes decorated function only if check passed
    """

    @functools.wraps(func)  # preserves signature of the function so it can be used in commands
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("Interaction is None")

        player = cast(AudioPlayer, interaction.guild.voice_client)
        if not player.playing:
            await interaction.response.send_message("Nothing is playing right now", delete_after=3, ephemeral=True)
            return
        await func(*args, **kwargs)

    return decorator


def button_cooldown(func):
    """
    Decorator for setting cooldown for buttons.\n
    Executes decorated method if button is off cooldown.\n
    The object of the decorated method has to have a property named _cooldown
    which determines the cooldown of the buttons.
    """

    @functools.wraps(func)  # preserves signature of the function so it can be used in commands
    async def decorator(self, *args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("Interaction is None")
        if not hasattr(self, '_cooldown'):
            raise ValueError("Object has no attribute named _cooldown")
        interaction.message.channel = interaction.channel
        bucket = self._cooldown.get_bucket(interaction.message)
        retry = bucket.update_rate_limit()
        if retry:
            await interaction.response.send_message("🤠 Slow down partner! 🤠", delete_after=3, ephemeral=True)
            return
        await func(self, *args, **kwargs)

    return decorator


def run_threadsafe(func):
    """
    Decorator for runing coroutine as threadsafe.\n
    Decorated corouting becomes a function so it doesnt have to be awaited
    """

    def decorator(*args, **kwargs):
        loop = next((arg for arg in args if isinstance(arg, asyncio.AbstractEventLoop)), None)
        if not loop:
            loop = next((kwarg for kwarg in kwargs.values() if isinstance(kwarg, asyncio.AbstractEventLoop)), None)
        if loop is None:
            raise ValueError("There is no EventLoop in argument of decorated function")
        if not inspect.iscoroutinefunction(func):
            raise TypeError('Decorated function is not a coroutine')
        coro = func(*args, **kwargs)
        asyncio.run_coroutine_threadsafe(coro, loop=loop)

    return decorator
