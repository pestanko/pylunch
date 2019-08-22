import flask
import os
import logging
import click
from pathlib import Path
from typing import List, Optional, Mapping

from pylunch import config, lunch, utils, __version__, log_config

log = logging.getLogger(__name__)


# Find the correct template folder when running from a different location
base_dir = Path(__file__).parent.parent
RESOURCES = base_dir / 'resources'
APP_NAME = 'PyLunch'
CONFIG_DIR = click.get_app_dir(APP_NAME.lower())
tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

def create_app():
    flask_app =flask.Flask(__name__, template_folder=tmpl_dir, static_folder=static_dir)
    if flask_app.debug:
        flask_app.jinja_env.auto_reload = True
        flask_app.config['TEMPLATES_AUTO_RELOAD'] = True
    return flask_app

app = create_app()

class WebApplication:
    INSTANCE = None
    def __init__(self, config_dir=None):
        self.service: lunch.LunchService = None
        config_dir = config_dir if config_dir is not None else CONFIG_DIR
        self.config_loader = config.YamlLoader(config_dir, 'config.yaml')
        self.restaurants_loader = config.YamlLoader(config_dir, 'restaurants.yaml')

    def init(self, **kwargs) -> 'WebApplication':
        log_config.load('i')
        if not self.config_loader.base_dir.exists():
            self._first_run()
        cfg_dict = {**self.config_loader.load(), **kwargs}
        cfg = config.AppConfig(**cfg_dict)
        loaded = self.restaurants_loader.load() or dict(restaurants={})
        unwrapped = loaded.get('restaurants') or loaded
        log.info(f"[INIT] Loaded: {[name for name in unwrapped.keys()]}")
        ent = lunch.Entities(**unwrapped)
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
 
    @classmethod
    def get(cls) -> 'WebApplication':
        if cls.INSTANCE is None:
            cls.INSTANCE = cls(config_dir=CONFIG_DIR)
            cls.INSTANCE.init()
        return cls.INSTANCE


def parse_request():
    rq = flask.request
    args = rq.args 
    result = dict(selectors=rq.args.getlist('r'), tags=rq.args.getlist('t'), format=rq.args.get('f', 'html'), roll=args.get('roll'))
    return result

def gen_context(**kw):
    return dict(version=__version__, **kw)

def roll_filter(items, roll):
    if not items:
        return []
    if not roll:
        return items
    import random
    return random.choices(items, k=int(roll))

@app.errorhandler(Exception)
def handle_error(e):
    code = 500
    if isinstance(e, flask.HTTPException):
        code = e.code
    context = gen_context(code=code, stacktrace=e, message=str(e))
    return flask.render_template('error.html', **context), code

@app.errorhandler(404)
def page_not_found(e: Exception):
    # note that we set the 404 status explicitly
    code = 404
    context = gen_context(code=code, stacktrace=e, message=str(e))
    return flask.render_template('error.html', **context), 404

@app.route('/')
def index():
    web_app = WebApplication.get()
    context = gen_context(tags=web_app.service.instances.all_tags(), restaurants=web_app.service.instances.all())
    return flask.render_template('index.html', **context)

@app.route('/restaurants/<name>')
def restaurant(name):
    web_app: WebApplication = WebApplication.get()
    entity = web_app.service.instances.find_one(name)
    menu = web_app.service.resolve_text(entity)
    context = gen_context(entity=entity, menu=menu)
    return flask.render_template('restaurant.html', **context)


@app.route("/menu")
def web_menu():
    args = parse_request()
    tags = args['tags']
    selectors = args['selectors']
    format = args['format']
    roll = args['roll']

    web_app = WebApplication.get()
    instances = None
    if selectors:
        instances = web_app.select_instances(instances)
    elif tags:
        instances = web_app.select_instances(tags, tags=True)
    else:
        instances = web_app.select_instances(selectors=None)
    
    instances = roll_filter(instances, roll)

    if format is None or format.lower() == 'text':
        content = "\n".join(resolve_menu(web_app.service, inst) for inst in instances)
        return flask.Response(content, mimetype='text/plain')
    else:
        menus = [(restaurant, web_app.service.resolve_text(restaurant)) for restaurant in instances if restaurant]
        context = gen_context(restaurants=instances, menus=menus)
        return flask.render_template('menu.html', **context)

###
# Helpers
### 

def resolve_menu(service: lunch.LunchEntity, instance):
    result = _generate_menu_header(instance)
    result += service.resolve_text(instance)
    return result 

def _generate_menu_header(instance):
    name_str = f"{instance.display_name} ({instance.name})"
    tags_str = "Tags: " + (", ".join(instance.tags) if instance.tags else '')
    return utils.generate_nice_header(name_str, instance.url, tags_str)
