import datetime
import logging
import yaml
import sys
from pathlib import Path
from typing import List, Tuple, Mapping
from shutil import copyfile

import click

from pylunch import log_config, lunch, __version__, config, utils

log = logging.getLogger(__name__)

base_dir = Path(__file__).parent.parent
RESOURCES = base_dir / 'resources'
APP_NAME = 'PyLunch'
CONFIG_DIR = click.get_app_dir(APP_NAME.lower())

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


class CliApplication:
    def __init__(self, config_dir=None):
        self.service: lunch.LunchService = None
        config_dir = config_dir if config_dir is not None else CONFIG_DIR
        self.config_loader = config.YamlLoader(config_dir, 'config.yaml')
        self.restaurants_loader = config.YamlLoader(config_dir, 'restaurants.yaml')

    def init(self, no_zomato=False, **kwargs) -> 'CliApplication':
        if not self.config_loader.base_dir.exists():
            self._first_run()
        cfg_dict = {**self.config_loader.load(), **kwargs}
        if no_zomato and 'zomato_key' in cfg_dict:
            del cfg_dict['zomato_key']
        cfg = config.AppConfig(**cfg_dict)
        loaded = self.restaurants_loader.load() or dict(restaurants={})
        unwrapped = loaded.get('restaurants') or loaded
        upsdated_str = loaded.get('updated')
        updated = datetime.datetime.fromisoformat(upsdated_str) if upsdated_str is not None else None
        ent = lunch.Entities(unwrapped, updated=updated)

        self.service = lunch.LunchService(cfg, ent)
        return self

    def _first_run(self):
        log.info(f"First run detected, crearing config folder: {self.config_loader.base_dir}")
        self.config_loader.base_dir.mkdir(parents=True)
        self.config_loader.save(data=dict(restaurants='./restaurants.yaml'))
        self.restaurants_loader.save(data={})

    def save_restaurants(self):
        log.info("Saving restaurants")
        self.restaurants_loader.save(self.service.instances.to_dict())

    def select_instances(self, selectors, fuzzy=False, tags=False, with_disabled=True) -> List[lunch.LunchEntity]:
        return self.service.instances.select(selectors, fuzzy=fuzzy, tags=tags, with_disabled=with_disabled)


pass_app = click.make_pass_decorator(CliApplication)


@click.group(help=f'{APP_NAME} CLI tool', context_settings=CONTEXT_SETTINGS)
@click.version_option(version=__version__)
@click.option('-L', '--log-level', help=f'Set log level (d|i|w|e) - default=w', default=None)
@click.option('-C', '--no-cache', help=f'Disable cache', is_flag=True, default=False)
@click.option('-c', '--config-dir', help=f'Location to the configuration directory', default=None)
@click.option('-F', '--format', help='Set output format', default=None)
@click.option('--no-zomato', help='Disable zomato even if enabled', default=False, is_flag=True)
@click.pass_context
def main_cli(ctx=None, log_level=None, format=None, no_cache=False, config_dir=None, no_zomato=False, **kwargs):
    log_config.load(log_level)
    app = CliApplication(config_dir=config_dir)
    ctx.obj = app.init(no_cache=no_cache, format=format, log_level=log_level, no_zomato=no_zomato)


@main_cli.command(name='ls', help='List all available restaurants')
@click.option('-l', '--limit', help="Limits number of restaurants to be shown", required=False, default=None)
@pass_app
def cli_list(app: CliApplication, limit=None):
    print(app.service.to_string())


@main_cli.command(name='version', help='Show version')
@pass_app
def cli_version(app: CliApplication):
    print(f"Version: {__version__}")


@main_cli.command(name='menu', help='Get menu for a restaurant')
@click.argument('selectors', nargs=-1)
@click.option("-t", "--tags", help="Search by tags", default=False, is_flag=True)
@click.option("-U", "--update-cache", '--update', help="Update cache entry", default=False, is_flag=True)
@click.option("--cut-before", help="Remove content before the substring", default=None)
@click.option("--cut-after", help="Remove content after the substring", default=None)
@click.option("--no-filters", help="Do not apply filters", default=False, is_flag=True)
@click.option("-F", "--full", help="Show full output - do not apply day filter", default=False, is_flag=True)
@click.option("-Q", "--with-fails", help="Show also fails at the end", default=False, is_flag=True)
@pass_app
def cli_menu(app: CliApplication, selectors: Tuple[str], tags=False, update_cache=False, **kwargs):
    instances = app.select_instances(selectors, tags=tags, with_disabled=False)
    if update_cache:
        cleared = app.service.cache.clear(instances)
    print_instances(app.service, instances, **kwargs)


@main_cli.command(name='roll', help='Get random menu for a restaurant')
@click.argument('selectors', nargs=-1)
@click.option("-t", "--tags", help="Search by tags", default=False, is_flag=True)
@click.option("-l", "--limit", help="Limit number of restaurants (default: 1)", default=1)
@pass_app
def cli_roll(app: CliApplication, selectors: Tuple[str], tags=False, limit=1, **kwargs):
    instances = app.select_instances(selectors, tags=tags, with_disabled=False)
    if instances:
        import random
        selected = random.choices(instances, k=limit)
        print_instances(app.service, selected, **kwargs)
    else:
        print("No instance found :-(")


@main_cli.command(name='info', help='Get info for the restaurant')
@click.argument('selectors', nargs=-1)
@click.option("-t", "--tags", help="Search by tags", default=False, is_flag=True)
@pass_app
def cli_info(app: CliApplication, selectors=None, tags=False):
    instances = app.select_instances(selectors, tags=tags)
    print_instances(app.service, instances, transform=str)


@main_cli.command(name='import', help='Import restaurants')
@click.argument('restaurants', nargs=-1)
@click.option("-O", "--override", help="Overide the restaurant if exists", default=False, is_flag=True)
@pass_app
def cli_import(app: CliApplication, restaurants=None, override=False):
    if not restaurants:
        print("Importing from the stdin. [EOF for END]")
        content = sys.stdin.read()
        log.info(f"Importing: {content}")
        app.service.import_string(content, override=override)
    else:
        for rest_file in restaurants:
            print(f"Importing restaurant: {rest_file}")
            app.service.import_file(rest_file, override=override)
    app.save_restaurants()


@main_cli.command(name='export', help='Export restaurants')
@click.option("-f", "--file", help="Export to file", default=None)
@pass_app
def cli_export(app: CliApplication, file=None):
    if file is None:
        if app.restaurants_loader.full_path.exists():
            content = app.restaurants_loader.full_path.read_text('utf-8')
            print(content)
        else:
            print(f"Error: Restaurants file not exists: {app.restaurants_loader.full_path}")

    else:
        # not a hack :-)
        copyfile(src=str(app.restaurants_loader.full_path), dst=file)


@main_cli.command(name='add', help='Adds a new restaurant')
@click.option("-n", "--name", help="Restaurant name", default=False)
@click.option("-d", "--display-name", help="Restaurant name", default=False)
@click.option("-u", "--url", help="Restaurant url", default=False)
@click.option("-s", "--selector", help="Restaurant css selector", default=False)
@click.option("-t", "--tags", help="Restaurant tags", default=False, multiple=True)
@click.option("-p", "--param", help="Additional param", default=False, multiple=True)
@click.option("-O", "--override", help="Overide the restaurant if exists", default=False, is_flag=True)
@pass_app
def cli_add(app: CliApplication, name, display_name, url, selector, tags, params, override=False):
    tags = list(tags) if tags else []
    config = dict(name=name, url=url, display_name=display_name, tags=tags, selector=selector)
    if params:
        config.update(**_params_dict(params), override=override)
    app.service.instances.register(**config)
    app.save_restaurants()


@main_cli.command(name='rm', help='Removes the restaurant')
@click.argument('selectors', nargs=-1)
@click.option("-f", "--fuzzy", help="Fuzzy search the name", default=False, is_flag=True)
@click.option("-t", "--tags", help="Search by tags", default=False, is_flag=True)
@pass_app
def cli_rm(app: CliApplication, selectors: Tuple[str], fuzzy=False, tags=False):
    instances = app.select_instances(selectors, fuzzy=fuzzy, tags=tags)
    for instance in instances:
        print(f"Removing: {instance.name}")
        del app.service.instances[instance.name]
    app.save_restaurants()


@main_cli.command(name='enable', help='Enables the restaurants')
@click.argument('selectors', nargs=-1)
@click.option("-f", "--fuzzy", help="Fuzzy search the name", default=False, is_flag=True)
@click.option("-t", "--tags", help="Search by tags", default=False, is_flag=True)
@pass_app
def cli_enable(app: CliApplication, selectors: Tuple[str], fuzzy=False, tags=False):
    instances = app.select_instances(selectors, fuzzy=fuzzy, tags=tags)
    for instance in instances:
        if 'disabled' in instance.keys():
            print(f"Enabling instance {instance.name}: {instance}")
            del app.service.instances[instance.name]['disabled']
    app.save_restaurants()


@main_cli.command(name='disable', help='Disables the restaurants')
@click.argument('selectors', nargs=-1)
@click.option("-f", "--fuzzy", help="Fuzzy search the name", default=False, is_flag=True)
@click.option("-t", "--tags", help="Search by tags", default=False, is_flag=True)
@pass_app
def cli_disable(app: CliApplication, selectors: Tuple[str], fuzzy=False, tags=False):
    instances = app.select_instances(selectors, fuzzy=fuzzy, tags=tags)
    for instance in instances:
        print(f"Disabling instance {instance.name}: {instance}")
        app.service.instances[instance.name]['disabled'] = True
    app.save_restaurants()


@main_cli.command(name='edit', help='Edits restaurants DB file')
@pass_app
def cli_edit_restaurants(app: CliApplication):
    cfg = app.restaurants_loader.load()
    content = yaml_edit(cfg)
    if content is None:
        print("No change - not saving")
    else:
        app.restaurants_loader.save(content)


@main_cli.command(name='config', help='Shows the current configuration')
@pass_app
def cli_config(app: CliApplication):
    import yaml
    cfg = app.service.config.config
    print(yaml.safe_dump(dict(Config=cfg)))


@main_cli.command(name='cache-clear', help='Clear a current cache for a day')
@click.argument('selectors', nargs=-1)
@click.option("-f", "--fuzzy", help="Fuzzy search the name", default=False, is_flag=True)
@click.option("-t", "--tags", help="Search by tags", default=False, is_flag=True)
@pass_app
def cli_cache_clear(app: CliApplication, selectors: Tuple[str], fuzzy=False, tags=False):
    if not app.service.config.use_cache:
        print("Not using the cache - no action.")
        return

    if not selectors:
        for item in app.service.cache.clear():
            print(f"Clearing: {item}")
    else:
        instances = app.select_instances(selectors, fuzzy=fuzzy, tags=tags)
        for item in app.service.cache.clear(instances):
            print(f"Clearing: {item}")


@main_cli.command(name='cache-content', help='Show the current cache for a day')
@pass_app
def cli_cache_content(app: CliApplication):
    if not app.service.config.use_cache:
        print("Not using the cache - no action.")
        return

    content = app.service.cache.content()
    if not content:
        print("No content in cache for today")
    else:
        for path in content:
            print(path)


@main_cli.command(name='cfg-set', help='Set a config value in the user configuration')
@click.argument('name')
@click.argument('value')
@pass_app
def cli_set_config(app: CliApplication, name, value):
    cfg = app.config_loader.load()
    cfg[name] = value
    app.config_loader.save(cfg)


@main_cli.command(name='cfg-edit', help='Edit a configuration using the editor (Ex: VIM)')
@pass_app
def cli_edit_config(app: CliApplication):
    cfg = app.config_loader.load()
    content = yaml_edit(cfg)
    if content is None:
        print("No change - not saving")
    else:
        app.config_loader.save(content)


@main_cli.command(name='console', help='Start the interactive console (IPython)')
@pass_app
def cli_start_console(app: CliApplication):
    try:
        import IPython
        print("Starting the interactive console using the IPython")
        IPython.embed()
    except ImportError:
        print('\nIPython modeule is not available')


@main_cli.command(name='telegram-bot', help='Start the telegram bot')
@pass_app
def cli_start_telegram_bot(app: CliApplication):
    try:
        from pylunch.bots.telegram_bot import PyLunchTelegramBot
        print("Starting the telegram bot")
        bot = PyLunchTelegramBot(app.service)
        bot.run()
    except ImportError:
        print('\n Telegram bot is not available module is not available')


@main_cli.command(name='discord-bot', help='Start the discord bot')
@pass_app
def cli_start_telegram_bot(app: CliApplication):
    try:
        from pylunch.bots.dc_bot import PyLunchDiscordBot, register_commands
        print("Starting the discord bot")
        bot = PyLunchDiscordBot.create(app.service)
        register_commands(bot.bot)
        bot.run()
    except ImportError:
        print('\n Telegram bot is not available module is not available')


@main_cli.group(name='sources', help='Manage default sources for autoupdate everyday')
def cli_sources():
    pass


@cli_sources.command(name='add', help='Add new source to update from')
@click.option('-U', '--url', help='It is remote source', is_flag=True, default=False)
@click.argument('name')
@click.argument('path')
@pass_app
def cli_sources_add(app: CliApplication, url: bool = False, name: str = None, path: str = None):
    pass


"""
" Helper tools
"""


def yaml_edit(cfg) -> dict:
    content = click.edit(yaml.safe_dump(cfg))
    if content is not None:
        return yaml.safe_load(content)
    return None


def _params_dict(params: List[str]) -> Mapping:
    result = {}
    for param in params:
        (key, val) = param.split('=')
        result[key] = val


def print_instances(service: lunch.LunchService, instances, transform=None, with_fails=False, **kwargs):
    fails = list() if with_fails else None
    transform = transform if transform is not None else lambda x: resolve_menu(service, x, fails=fails, **kwargs)
    utils.write_instances(instances, transform=transform, writer=print)
    if fails:
        print("\n~~~~~~~~~~~~~~~~  FAILS  ~~~~~~~~~~~~~~~\n")
        for fail in fails:
            print(fail)


def resolve_menu(service: lunch.LunchService, instance: lunch.LunchEntity, fails: list = None, **kwargs):
    result = _generate_menu_header(instance)
    content = service.resolve_text(instance, **kwargs)
    if not content:
        if fails is not None:
            fails.append(instance)
        result += f"No content provided for: {instance.name}"
    else:
        result += content
    return result


def _generate_menu_header(instance):
    name_str = f"{instance.display_name} ({instance.name})"
    tags_str = "Tags: " + (", ".join(instance.tags) if instance.tags else '')
    return utils.generate_nice_header(name_str, instance.url, tags_str)


if __name__ == '__main__':
    main_cli()
