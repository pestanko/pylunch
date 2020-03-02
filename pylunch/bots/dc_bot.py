from discord.ext import commands

from pylunch import lunch

import logging

log = logging.getLogger(__name__)

discord_bot = commands.Bot(command_prefix='$')


def register_commands(bot: commands.Bot):
    bot.add_command(discord_cmd_menu)


class PyLunchDiscordContext(commands.Context):
    def __init__(self, service: lunch.LunchService, **attrs):
        super().__init__(**attrs)
        self._service = service

    @property
    def service(self) -> lunch.LunchService:
        return self._service


class PyLunchDiscordBot(commands.Bot):
    async def get_context(self, message, *, cls=PyLunchDiscordContext):
        # when you override this method, you pass your new Context
        # subclass to the super() method, which tells the bot to
        # use the new MyContext class
        return await super().get_context(message, cls=cls)


@commands.command(name='menu')
async def discord_cmd_menu(ctx: PyLunchDiscordContext, *args):
    tags = " ".join(args)
    instances = ctx.service.instances.select(tags, fuzzy=True, tags=True)
    log.debug(f"Printing: {instances}")

    if instances is None or not instances:
        await ctx.send("**No instance has been found**")

    for instance in instances:
        if instance is not None:
            log.info(f"Sending one response from list: {instances}")
            content = ctx.service.resolve_text(instance)
            await ctx.send(content)