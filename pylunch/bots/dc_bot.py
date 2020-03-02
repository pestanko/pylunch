import discord
from discord.ext import commands

from pylunch import lunch

import logging

log = logging.getLogger(__name__)

discord_bot = commands.Bot(command_prefix='$')


def register_commands(bot: commands.Bot):
    bot.add_command(discord_cmd_menu)


class PyLunchDiscordBot:
    __instance = None

    @classmethod
    def get(cls) -> 'PyLunchDiscordBot':
        return cls.__instance

    @classmethod
    def create(cls, *args, **kwargs):
        cls.__instance = cls(*args, **kwargs)
        return cls.__instance

    def __init__(self, service: lunch.LunchService, prefix="$"):
        self._service = service
        self._bot = commands.Bot(prefix)

    @property
    def service(self) -> lunch.LunchService:
        return self._service


@commands.command(name='menu')
async def discord_cmd_menu(ctx: commands.Context, *args):
    app = PyLunchDiscordBot.get()
    tags = " ".join(args)
    instances = app.service.instances.select(tags, fuzzy=True, tags=True)
    log.debug(f"Printing: {instances}")

    if instances is None or not instances:
        await ctx.send("**No instance has been found**")

    for instance in instances:
        if instance is not None:
            log.info(f"Sending one response from list: {instances}")
            content = app.service.resolve_text(instance)
            await ctx.send(content)


@commands.command(name='tags')
async def discord_cmd_tags(ctx: commands.Context):
    app = PyLunchDiscordBot.get()
    tags = app.service.instances.all_tags()
    content = "TAGS:\n\n" + ("\n".join(tags))
    log.info(f"Sending the tags: {tags}")
    await ctx.send(content)

