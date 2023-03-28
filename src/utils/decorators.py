import functools

import discord


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

        bot_vc = interaction.guild.voice_client
        if not bot_vc:
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

        user_vc = interaction.user.voice
        if not user_vc:
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

        bot_vc, user_vc = interaction.guild.voice_client, interaction.user.voice
        if not (bot_vc and user_vc and bot_vc.channel.id == user_vc.channel.id):
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

        bot_vc = interaction.guild.voice_client
        if not bot_vc.is_playing():
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
