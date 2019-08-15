import flask
import os
import logging
import click
from pathlib import Path
from typing import List, Optional, Mapping

from pylunch import config, lunch, utils

log = logging.getLogger(__name__)


# Find the correct template folder when running from a different location
base_dir = Path(__file__).parent.parent
RESOURCES = base_dir / 'resources'
APP_NAME = 'PyLunch'
CONFIG_DIR = click.get_app_dir(APP_NAME.lower())
tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

app = flask.Flask(__name__, template_folder=tmpl_dir)


class WebApplication:
    def __init__(self, config_dir=None):
        self.service: lunch.LunchService = None
        config_dir = config_dir if config_dir is not None else CONFIG_DIR
        self.config_loader = config.YamlLoader(config_dir, 'config.yaml')
        self.restaurants_loader = config.YamlLoader(config_dir, 'restaurants.yaml')

    def init(self, **kwargs) -> 'WebApplication':
        if not self.config_loader.base_dir.exists():
            self._first_run()
        cfg_dict = {**self.config_loader.load(), **kwargs}
        cfg = config.AppConfig(**cfg_dict)
        loaded = self.restaurants_loader.load() or dict(restaurants={})
        unwrapped = loaded.get('restaurants') or loaded
        ent = lunch.Entities(**unwrapped)
        
        self.service = lunch.CachedLunchService(cfg, ent) if cfg.use_cache else lunch.LunchService(cfg, ent)
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
 
    @classmethod
    def create(cls) -> 'WebApplication':
        app = cls(config_dir=CONFIG_DIR)
        app.init()
        return app


def parse_request():
    rq = flask.request
    args = rq.args 
    result = dict(selectors=rq.args.getlist('r'), tags=rq.args.getlist('t'))
    return result


@app.route("/menu")
def web_menu():
    args = parse_request()
    tags = args['tags']
    selectors = args['selectors']

    app = WebApplication.create()
    instances = None
    if selectors:
        instances = app.select_instances(instances)
    elif tags:
        instances = app.select_instances(tags, tags=True)
    else:
        instances = app.select_instances(selectors=None)
    content = "\n".join(resolve_menu(app.service, inst) for inst in instances)
    return flask.Response(content, mimetype='text/plain')


###
# Helpers
### 

def resolve_menu(service: lunch.LunchEntity, instance):
    result = _generate_menu_header(instance)
    if service.config.format == 'html':
        result += service.resolve_html(instance)
    else:
        result += service.resolve_text(instance)
    return result 

def _generate_menu_header(instance):
    name_str = f"{instance.display_name} ({instance.name})"
    tags_str = "Tags: " + (", ".join(instance.tags) if instance.tags else '')
    return utils.generate_nice_header(name_str, instance.url, tags_str)
