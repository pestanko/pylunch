from discord.ext import commands

from pylunch import lunch

import logging

log = logging.getLogger(__name__)

discord_bot = commands.Bot(command_prefix='$')


def register_commands(bot: commands.Bot):
    bot.add_command(discord_cmd_menu)
    bot.add_command(discord_cmd_tags)
    bot.add_command(discord_cmd_restaurants)
    bot.add_command(discord_cmd_tmenu)


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

    @property
    def bot(self) -> commands.Bot:
        return self._bot

    def run(self):
        token = self.service.config.discord_token
        log.info(f"Using the token: {token}")
        self.bot.run(token)


@commands.command(name='tmenu', help="Show menus for the restaurants by tags")
async def discord_cmd_tmenu(ctx: commands.Context, *args):
    app = PyLunchDiscordBot.get()
    instances = app.service.instances.select(args, fuzzy=True, tags=True)
    log.debug(f"Printing: {instances}")

    if instances is None or not instances:
        await ctx.send("**No instance has been found**")

    for instance in instances:
        if instance is not None:
            log.info(f"Sending one response from list: {instances}")
            content = app.service.resolve_text(instance)
            content = f"---\n{instance.name} ({instance.display_name})\n{instance.url}\n\n{content}"
            await ctx.send(content[:1999])


@commands.command(name='tags', help="List all tags")
async def discord_cmd_tags(ctx: commands.Context):
    app = PyLunchDiscordBot.get()
    tags = app.service.instances.all_tags()
    content = "TAGS:\n\n" + ("\n".join(tags))
    log.info(f"Sending the tags: {tags}")
    await ctx.send(content)


@commands.command(name='restaurants', help="List all available restaurants")
async def discord_cmd_restaurants(ctx: commands.Context, *args):
    app = PyLunchDiscordBot.get()
    instances = app.service.instances.select(args, fuzzy=True, tags=True)
    log.debug(f"Printing: {instances}")

    if instances is None or not instances:
        await ctx.send("**No instance has been found**")

    message = "Restaurants:\n\n"
    for instance in instances:
        if instance is None:
            continue

        line = f"{instance.name} ({instance.display_name}) {instance.url}"
        if len(message) + len(line) + 5 >= 2000:
            log.info(f"Sending one response from list: {message}")
            await ctx.send(message)
            message = line
        else:
            message = f"{message}\n{line}"

    log.info(f"Sending one response from list: {message}")
    await ctx.send(message)


@commands.command(name='menu', help="Show menu for the provided restaurant")
async def discord_cmd_menu(ctx: commands.Context, *args):
    app = PyLunchDiscordBot.get()
    instances = app.service.instances.select(args, fuzzy=True)
    log.debug(f"Printing: {instances}")

    if instances is None or not instances:
        await ctx.send("**No instance has been found**")

    for instance in instances:
        if instance is not None:
            log.info(f"Sending one response from list: {instances}")
            content = app.service.resolve_text(instance)
            content = f"---\n{instance.name} ({instance.display_name})\n{instance.url}\n\n{content}"
            await ctx.send(content[:1999])
