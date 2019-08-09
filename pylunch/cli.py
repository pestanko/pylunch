import logging
import tempfile
from pathlib import Path
from typing import List, Tuple, Mapping
from shutil import copyfile

import click

from pylunch import log_config, lunch, __version__, config

log = logging.getLogger(__name__)

base_dir = Path(__file__).parent.parent
RESOURCES = base_dir / 'resources'
APP_NAME = 'PyLunch'
CONFIG_DIR = click.get_app_dir(APP_NAME.lower())


class CliApplication:
    def __init__(self, config_dir=None):
        self.service: lunch.LunchService = None
        config_dir = config_dir if config_dir is not None else CONFIG_DIR
        self.config_loader = config.YamlLoader(config_dir, 'config.yaml')
        self.restaurants_loader = config.YamlLoader(config_dir, 'restaurants.yaml')

    def init(self, **kwargs) -> 'CliApplication':
        if not self.config_loader.base_dir.exists():
            self._first_run()
        cfg_dict = {**self.config_loader.load(), **kwargs}
        cfg = config.AppConfig(**cfg_dict)
        loaded = self.restaurants_loader.load() or dict(restaurants={})
        unwrapped = loaded.get('restaurants') or loaded
        ent = lunch.Entities(**unwrapped)
        
        self.service = lunch.CachedLunchService(cfg, ent) if cfg.use_cache else lunch.LunchService(cfg, ent)
#        self.service.import_file(RESOURCES / 'restaurants.yml')
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
        def _get() -> List['lunch.LunchEntity']:
            if selectors is None or len(selectors) == 0:
                return list(self.service.instances.values())
            if tags:
                full = " ".join(selectors)
                return self.service.instances.find_by_tags(full)
            if fuzzy:
                return [ self.service.instances.fuz_find_one(select) for select in selectors ]
            return [ self.service.instances.get(select) for select in selectors ]

        if with_disabled:
            return _get()

        instances = _get()
        return [ item for item in instances if item and not item.disabled]
 

pass_app = click.make_pass_decorator(CliApplication)

@click.group(help=f'{APP_NAME} CLI tool')
@click.version_option(version=__version__)
@click.option('-L', '--log-level', help=f'Set log level (d|i|w|e) - default=w', default=None)
@click.option('-C', '--no-cache', help=f'Disable cache', is_flag=True, default=False)
@click.option('-c', '--config-dir', help=f'Location to the configuration directory', default=None)
@click.option('-F', '--format', help='Set output format', default=None)
@click.pass_context
def main_cli(ctx=None, log_level=None, format=None, no_cache=False, config_dir=None, **kwargs):
    log_config.load(log_level)
    app = CliApplication(config_dir=config_dir)
    ctx.obj = app.init(no_cache=no_cache, format=format)


@main_cli.command(name='ls', help='List restaurants')
@click.option('-l', '--limit', help="Limits number of restaurants to be shown", required=False, default=None)
@pass_app
def cli_list(app: CliApplication, limit=None):
    print(app.service.to_string())
    

@main_cli.command(name='menu', help='Get menu for a restaurant')
@click.argument('selectors', nargs=-1)
@click.option("-f", "--fuzzy", help="Fuzzy search the name", default=False, is_flag=True)
@click.option("-t", "--tags", help="Search by tags", default=False, is_flag=True)
@pass_app
def cli_menu(app: CliApplication, selectors: Tuple[str], fuzzy=False, tags=False):
    instances = app.select_instances(selectors, fuzzy=fuzzy, tags=tags, with_disabled=False)
    print_instances(app.service, instances)


@main_cli.command(name='info', help='Get info for the restaurant')
@click.argument('selectors', nargs=-1)
@click.option("-f", "--fuzzy", help="Fuzzy search the name", default=False, is_flag=True)
@click.option("-t", "--tags", help="Search by tags", default=False, is_flag=True)
@pass_app
def cli_info(app: CliApplication, selectors=None, fuzzy=False, tags=False):
    instances = app.select_instances(selectors, fuzzy=fuzzy, tags=tags)
    print_instances(app.service, instances, printer=lambda _, x: print(x))


@main_cli.command(name='import', help='Import restaurants')
@click.argument('restaurants', nargs=-1)
@click.option("-O", "--override", help="Overide the restaurant if exists", default=False, is_flag=True)
@pass_app
def cli_import(app: CliApplication, restaurants=None, override=False):
    if not restaurants:
        print("Not provided any files to import from")
    for rest_file in restaurants:
        app.service.import_file(rest_file)
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


@main_cli.command(name='add', help='Adds new restaurant')
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
def cli_enable(app: CliApplication, selectors: Tuple[str], fuzzy=False, tags=False):
    instances = app.select_instances(selectors, fuzzy=fuzzy, tags=tags)
    for instance in instances:
        print(f"Disabling instance {instance.name}: {instance}")
        app.service.instances[instance.name]['disabled'] = True
    app.save_restaurants()

"""
" Helper tools
"""

def _params_dict(params: List[str]) -> Mapping:
    result = {}
    for param in params:
        (key, val) = param.split('=')
        result[key] = val

def print_instances(service: lunch.LunchService, instances, printer=None):
    printer = printer if printer is not None else print_text
    if instances is None or not instances:
        print("Not found any instance")

    elif isinstance(instances, list):
        for instance in instances:
            if instance is not None:
                printer(service, instance)
            else:
                print("Instance not Found")
    else:
        printer(service, instances)

def print_text(service: lunch.LunchEntity, instance):
    result = None
    if service.config.format == 'html':
        result = service.resolve_html(instance)
    else:
        result = service.resolve_text(instance)
    
    _header_print(instance)
    print("\n")
    print(result)   

def _header_print(instance):
    name_str = f"{instance.display_name} ({instance.name})"
    tags_str = "Tags: " + (", ".join(instance.tags) if instance.tags else '')
    print_nice_header(name_str, instance.url, tags_str)


def print_nice_header(*strings):
    def _for_print(max_l, curr, char='='):
        for i in range(max_l - curr): 
            print(char, end='')

    def _print_text(max_l, text):
        print(f"\n===  {text}", end='')
        _for_print(max_l, len(text), char=' ') 
        print("  ===", end='')

    def _beg_end_line(max_l):
        print("")
        _for_print(max_l + 10, 0)

    max_len = max(len(text) for text in strings)
    _beg_end_line(max_len)
    for text in strings:
        _print_text(max_len, text)
    _beg_end_line(max_len)


if __name__ == '__main__':
    main_cli()