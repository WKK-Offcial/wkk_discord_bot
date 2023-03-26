import functools
import discord

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
            await interaction.response.send_message("You can't control the bot because you're not on the same voice channel",
                                                    delete_after=3, ephemeral=True)
            return
        await func(*args, **kwargs)

    return decorator

def user_is_in_voice_channel_check(func):
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

        user_vc = interaction.user.voice
        if not user_vc:
            await interaction.response.send_message("You can't control the bot because you're not in a voice channel",
                                                    delete_after=3, ephemeral=True)
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
            await interaction.response.send_message("Nothing is playing right now",
                                                        delete_after=3, ephemeral=True)
            return
        await func(*args, **kwargs)
    return decorator
