import logging
import tempfile
from pathlib import Path
from typing import List, Tuple

import click

from pylunch import log_config, lunch, __version__, config

log = logging.getLogger(__name__)

base_dir = Path(__file__).parent.parent
RESOURCES = base_dir / 'resources'
APP_NAME = 'PyLunch'
CONFIG_DIR = click.get_app_dir(APP_NAME.lower())

class CliApplication:
    def __init__(self):
        self.service: lunch.LunchService = None
        self.config_loader = config.YamlLoader(CONFIG_DIR, 'config.yaml')
        self.restaurants_loader = config.YamlLoader(CONFIG_DIR, 'restaurants.yaml')

    def init(self, **kwargs) -> 'CliApplication':
        cfg_dict = {**self.config_loader.load(), **kwargs}
        cfg = config.AppConfig(**cfg_dict)
        ent = lunch.Entities(**self.restaurants_loader.load())
        self.service = lunch.CachedLunchService(cfg, ent) if cfg.use_cache else lunch.LunchService(cfg, ent)
        self.service.import_file(RESOURCES / 'restaurants.yml')
        return self


@click.group(help=f'{APP_NAME} CLI tool')
@click.version_option(version=__version__)
@click.option('-L', '--log-level', help=f'Set log level (d|i|w|e) - default=w', default=None)
@click.option('-C', '--no-cache', help=f'disable cache', is_flag=True, default=False)
@click.pass_context
def main_cli(ctx=None, log_level=None, no_cache=False, **kwargs):
    log_config.load(log_level)
    app = CliApplication()
    ctx.obj = app.init(no_cache=no_cache)

@main_cli.command(name='ls', help='List restaurants')
@click.option('-l', '--limit', help="Limits number of restaurants to be shown", required=False, default=None)
@click.pass_obj
def cli_list(obj: CliApplication, limit=None):
    print(obj.service.to_string())


@main_cli.command(name='sel', help='Select menu for restaurants by tags')
@click.argument('select')
@click.pass_obj
def cli_select(obj: CliApplication, select=None):
    selected = obj.service.instances.find_by_tags(select)
    print_instances(obj.service, selected)
    

@main_cli.command(name='menu', help='Get menu for a restaurant')
@click.argument('name', nargs=-1)
@click.option("-f", "--fuzzy", help="Fuzzy search the name", default=False, is_flag=True)
@click.pass_obj
def cli_menu(obj: CliApplication, name: Tuple[str], fuzzy=False):
    def _once(rest_name, fuzz):
        instance = obj.service.instances.get(rest_name) if not fuzz else obj.service.fuz_find_one(rest_name)
        print_instances(obj.service, instance)

    if name.lower().strip() == "all":
        for key in obj.service.instances.keys():
            _once(key, False)
    else:
        _once(name, fuzzy)


@main_cli.command(name='info', help='Get info for the restaurant')
@click.argument('name')
@click.option("-f", "--fuzzy", help="Fuzzy search the name", default=False, is_flag=True)
def cli_info(obj: CliApplication, name=None, fuzzy=False):
    def _once(rest_name, fuzz):
        instance = obj.service.instances.get(rest_name) if not fuzz else obj.service.fuz_find_one(rest_name)
        print_instances(obj.service, instance, printer=lambda _, x: print(x))

    if name is None or name == '':
        for key in obj.service.instances.keys():
            _once(key, False)
    else:
        _once(name, fuzzy)

def print_instances(service: lunch.LunchService, instances, printer=None):
    printer = printer if printer is not None else print_text
    if instances is None:
        print("Not found any instance")

    elif isinstance(instances, list):
        for instance in instances:
            printer(service, instance)
    else:
        printer(service, instances)

def print_text(service, instance):
    result = service.resolve_text(instance)
    print(f"\n-------  {instance.display_name} ({instance.name})  -------\n")
    print(result)


if __name__ == '__main__':
    main_cli()