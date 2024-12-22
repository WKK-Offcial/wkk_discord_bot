import asyncio
import functools
import inspect
from typing import cast
from audio_player import AudioPlayer

import discord


def bot_is_in_voice_channel_check(func):
    """
    Decorator to check whether the bot is in a voice channel.
    Executes the decorated function only if the check passes.
    """

    @functools.wraps(func)
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("No discord.Interaction found in arguments.")

        player = cast(AudioPlayer, interaction.guild.voice_client)
        if not player:
            await interaction.response.send_message(
                "The bot is not in a voice channel.", delete_after=3, ephemeral=True
            )
            return

        await func(*args, **kwargs)

    return decorator


def user_is_in_voice_channel_check(func):
    """
    Decorator to check whether the user is in a voice channel.
    Executes the decorated function only if the check passes.
    """

    @functools.wraps(func)
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("No discord.Interaction found in arguments.")

        if not interaction.user.voice:
            await interaction.response.send_message(
                "You must be in a voice channel to control the bot.", delete_after=3, ephemeral=True
            )
            return

        await func(*args, **kwargs)

    return decorator


def user_bot_in_same_channel_check(func):
    """
    Decorator to check whether the user is in the same voice channel as the bot.
    Executes the decorated function only if the check passes.
    """

    @functools.wraps(func)
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("No discord.Interaction found in arguments.")

        player = cast(AudioPlayer, interaction.guild.voice_client)
        user_voice = interaction.user.voice

        if not (player and user_voice and player.channel.id == user_voice.channel.id):
            await interaction.response.send_message(
                "You must be in the same voice channel as the bot to control it.", delete_after=3, ephemeral=True
            )
            return

        await func(*args, **kwargs)

    return decorator


def is_playing_check(func):
    """
    Decorator to check whether the bot is currently playing audio.
    Executes the decorated function only if the check passes.
    """

    @functools.wraps(func)
    async def decorator(*args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("No discord.Interaction found in arguments.")

        player = cast(AudioPlayer, interaction.guild.voice_client)
        if not player or not player.playing:
            await interaction.response.send_message("Nothing is playing right now.", delete_after=3, ephemeral=True)
            return

        await func(*args, **kwargs)

    return decorator


def button_cooldown(func):
    """
    Decorator to enforce cooldowns for buttons.
    The object of the decorated method must have a `_cooldown` property.
    """

    @functools.wraps(func)
    async def decorator(self, *args, **kwargs):
        interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
        if interaction is None:
            raise ValueError("No discord.Interaction found in arguments.")

        if not hasattr(self, "_cooldown"):
            raise ValueError("The object does not have a `_cooldown` property.")

        bucket = self._cooldown.get_bucket(interaction.message)
        retry = bucket.update_rate_limit()
        if retry:
            await interaction.response.send_message("🤠 Slow down, partner! 🤠", delete_after=3, ephemeral=True)
            return

        await func(self, *args, **kwargs)

    return decorator


def run_threadsafe(func):
    """
    Decorator to run a coroutine in a thread-safe manner.
    The decorated function will be run as a thread-safe coroutine.
    """

    def decorator(*args, **kwargs):
        loop = next(
            (arg for arg in args if isinstance(arg, asyncio.AbstractEventLoop)),
            next((kwarg for kwarg in kwargs.values() if isinstance(kwarg, asyncio.AbstractEventLoop)), None),
        )
        if not loop:
            raise ValueError("No asyncio.AbstractEventLoop found in arguments.")

        if not inspect.iscoroutinefunction(func):
            raise TypeError("The decorated function must be a coroutine.")

        coro = func(*args, **kwargs)
        asyncio.run_coroutine_threadsafe(coro, loop=loop)

    return decorator
