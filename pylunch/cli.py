import logging
from pathlib import Path
from typing import List, Tuple

import click

from pylunch import log_config, lunch, __version__

log = logging.getLogger(__name__)

base_dir = Path(__file__).parent.parent.parent


class CliApplication:
    def __init__(self, service: lunch.LunchService):
        self.service = service
        self.service.register_instances()


@click.group(help='DPMB CLI tool')
@click.version_option(version=__version__)
@click.option('-v', '--verbose', help=f'Set verbose', is_flag=True, default=False)
@click.pass_context
def main_cli(ctx=None, verbose=False, **kwargs):
    if verbose:
        log_config.load()
    service = lunch.LunchService()
    ctx.obj = CliApplication(service)

@main_cli.command(name='ls', help='List restaurants')
@click.option('-l', '--limit', help="Limits number of restaurants to be shown", required=False, default=None)
@click.pass_obj
def cli_list(obj: CliApplication, limit=None):
    print(obj.service.to_string())


@main_cli.command(name='menu', help='Get menu for a restaurant')
@click.argument('name')
@click.option("-f", "--fuzzy", help="Fuzzy search the name", default=False, is_flag=True)
@click.pass_obj
def cli_menu(obj: CliApplication, name: str=None, fuzzy=False):
    def _once(rest_name, fuzz):
        instance = obj.service.get(rest_name) if not fuzz else obj.service.fuz_find_one(rest_name)
        if instance is None:
            print(f"Not found instance for: \"{rest_name}\"")
        else:
            result = instance.invoke()
            print(f"\n-------  {instance.name}  -------\n")
            print(result)

    if name.lower().strip() == "all":
        for key in obj.service.instances.keys():
            _once(key, False)


@main_cli.command(name='info', help='Get info for the restaurant')
@click.argument('name')
@click.option("-f", "--fuzzy", help="Fuzzy search the name", default=False, is_flag=True)
def cli_info(obj: CliApplication, name=None, fuzzy=False):
    def _once(rest_name, fuzz):
        instance = obj.service.get(rest_name) if not fuzz else obj.service.fuz_find_one(rest_name)
        if instance is None:
            print(f"Not found instance for: \"{rest_name}\"")
        else:
            print(instance)

    if name.lower().strip() == "all":
        for key in obj.service.instances.keys():
            _once(key, False)



if __name__ == '__main__':
    main_cli()