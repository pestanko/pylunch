import flask
import functools
import os
from urllib.error import HTTPError
import logging
import click
import datetime
from pathlib import Path
from typing import List, Optional, Mapping, Union
from pylunch import config, lunch, utils, __version__, log_config, errors
from werkzeug.security import generate_password_hash, check_password_hash

from flask_jwt_extended import (
    JWTManager, jwt_required, create_access_token,
    jwt_refresh_token_required, create_refresh_token,
    get_jwt_identity, set_access_cookies,
    set_refresh_cookies, unset_jwt_cookies
)

log = logging.getLogger(__name__)


# Find the correct template folder when running from a different location
base_dir = Path(__file__).parent.parent
RESOURCES = base_dir / 'resources'
APP_NAME = 'PyLunch'
CONFIG_DIR = click.get_app_dir(APP_NAME.lower())
tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

class AdminUsers(utils.CollectionWrapper):
    @property
    def users(self) -> Mapping:
        return self.collection

    def import_users(self, file: str):
        log.info(f"[IMPORT] Importing users from: {file}")
        loaded = utils.load_yaml(file)
        if not loaded:
            return
        
        for (name, password) in loaded.items():
            log.info(f"[IMPORT] Importing user: {name}")
            self[name] = password

    def generate_hash(self, password):
        return generate_password_hash(password)

    def check_password(self, name, passwd) -> bool:
        userhash = self.get(name)
        if not userhash:
            log.info(f"[USER] Password check failed: User {name} not exists.")
            return False
        if check_password_hash(userhash, passwd):
            log.info(f"[USER] User password accepted for {name}")
            return True
        log.info(f"[USER] User password rejected for {name} - mismatch")
        return False

    def issue_tokens(self, name) -> dict:
        access_token = create_access_token(identity = name)
        refresh_token = create_refresh_token(identity = name)
        return dict(access_token=access_token, refresh_token = refresh_token, username=name)

    def issue_access_token(self, name) -> dict:
        access_token = create_access_token(identity = name)
        return dict(access_token=access_token, username=name)


def handle_general_error(e):
    code = 500
    if isinstance(e, HTTPError):
        code = e.code
    web_app = WebApplication.get()
    context = web_app.gen_context(code=code, stacktrace=e, message=str(e), flash='')
    return flask.render_template('error.html', **context), code

def handle_api_error(e: errors.PyLunchApiError):
    return flask.jsonify(e.to_json()), e.code

def page_not_found(e: Exception):
    # note that we set the 404 status explicitly
    code = 404
    web_app = WebApplication.get()
    context = web_app.gen_context(code=code, stacktrace=e, message=str(e))
    return flask.render_template('error.html', **context), 404

    
class WebApplication:
    INSTANCE = None

    @classmethod
    def create_app(cls):
        flask_app = flask.Flask(__name__, template_folder=tmpl_dir, static_folder=static_dir)
        flask_app.config['JWT_SECRET_KEY'] = os.getenv('PYLUNCH_SECRET', 'jwt-secret-string')
        flask_app.config['JWT_TOKEN_LOCATION'] = ('cookies', 'headers')
        flask_app.config['JWT_ACCESS_COOKIE_PATH'] = '/'
        flask_app.config['JWT_REFRESH_COOKIE_PATH'] = '/'
        flask_app.config['JWT_COOKIE_CSRF_PROTECT'] = False

        flask_app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(days=7)
        flask_app.config['JWT_REFRESH_TOKEN_EXPIRES'] = datetime.timedelta(days=30)

        JWTManager(flask_app)
        if flask_app.debug:
            flask_app.jinja_env.auto_reload = True
            flask_app.config['TEMPLATES_AUTO_RELOAD'] = True
        else:
            flask_app.register_error_handler(404, page_not_found)
            flask_app.register_error_handler(Exception, handle_general_error)
            flask_app.register_error_handler(errors.PyLunchApiError, handle_api_error)
        return flask_app

    def __init__(self, config_dir=None):
        self._service: lunch.LunchService = None
        config_dir = config_dir if config_dir is not None else CONFIG_DIR
        self.config_loader = config.YamlLoader(config_dir, 'config.yaml')
        self.restaurants_loader = config.YamlLoader(config_dir, 'restaurants.yaml')
        self.users = AdminUsers()

    @property
    def service(self) -> lunch.LunchService:
        return self._service

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
        self._service = lunch.LunchService(cfg, ent)
        self.users.import_users(os.getenv('PYLUNCH_USERS', RESOURCES / 'users.yml'))
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

    def gen_context(self, **kwargs):
        tags = self.service.instances.all_tags()
        restaurants = self.service.instances.all()
        return dict(version=__version__, all_tags=tags, all_restaurants=restaurants, **kwargs)
 
    @classmethod
    def get(cls) -> 'WebApplication':
        if cls.INSTANCE is None:
            cls.INSTANCE = cls(config_dir=CONFIG_DIR)
            cls.INSTANCE.init()
        return cls.INSTANCE


    def parse_request(self):
        rq = flask.request
        args = rq.args 
        result = dict(selectors=rq.args.getlist('r'), tags=rq.args.getlist('t'), format=rq.args.get('f', 'h'), roll=args.get('roll'))
        return result

    def select_by_request(self):
        args = self.parse_request()
        tags = args['tags']
        selectors = args['selectors']
        format: str = args['format']
        roll = args['roll']
        def _inner():
            if selectors:
                return self.select_instances(selectors)
            elif tags:
                return self.select_instances(tags, tags=True)
            else:
                return self.select_instances(selectors=None)
        result = _inner()
        return roll_filter(result, roll)


app = WebApplication.create_app()
api = flask.Blueprint('api', __name__)
admin = flask.Blueprint('admin', __name__)

def register_blueprints(app):
    app.register_blueprint(api, url_prefix='/api')
    app.register_blueprint(admin, url_prefix='/admin')


def roll_filter(items, roll):
    if not items:
        return []
    if not roll:
        return items
    import random
    return random.choices(items, k=int(roll))

@app.route('/')
def index():
    web_app = WebApplication.get()
    context = web_app.gen_context()
    return flask.render_template('index.html', **context)

@app.route('/restaurants/<name>')
def restaurant(name):
    web_app: WebApplication = WebApplication.get()
    entity = web_app.service.instances.find_one(name)
    menu = web_app.service.resolve_text(entity)
    context = web_app.gen_context(entity=entity, menu=menu)
    return flask.render_template('restaurant.html', **context)


@app.route('/menu')
def web_async_menu():
    web_app = WebApplication.get()
    context = web_app.gen_context()
    return flask.render_template('menu.html', **context)

@app.route("/fmenu")
def web_fallback_menu():
    web_app = WebApplication.get()
    instances = web_app.select_by_request()
    instances = instances if instances is not None else []
    format = web_app.parse_request()['format']

    if format is not None and format.startswith('t'):
        content = "\n".join(resolve_menu(web_app.service, inst) for inst in instances)
        return flask.Response(content, mimetype='text/plain')
    else:
        menus = [(restaurant, web_app.service.resolve_text(restaurant)) for restaurant in instances if restaurant]
        context = web_app.gen_context(restaurants=instances, menus=menus)
        return flask.render_template('fmenu.html', **context)


###
# API
###

@api.route("/restaurants")
def route_api_restaurants():
    web_app = WebApplication.get()
    instances = web_app.select_by_request()
    return flask.jsonify({item.name: item.config for item in instances if item})

@api.route("/tags")
def route_api_tags():
    web_app = WebApplication.get()
    tags = web_app.service.instances.all_tags()
    return flask.jsonify(tags)

@api.route("/restaurants/<name>")
def route_api_restaurants_get(name):
    web_app = WebApplication.get()
    instance = web_app.service.instances.find_one(name)
    return flask.jsonify(instance.config)


@api.route("/restaurants/<name>/menu")
def route_api_restaurants_get_menu(name):
    web_app = WebApplication.get()
    instance = web_app.service.instances.find_one(name)
    content = web_app.service.resolve_text(instance)
    if content:
        result = {**instance.config, 'content': content}
        return flask.jsonify(result)
    else:
        return flask.jsonify(errors.UnnableToLoadContent(name).to_json()), 400


@api.route("/restaurants/<name>/cache")
def route_api_restaurants_get_cache(name):
    web_app = WebApplication.get()
    instance = web_app.service.instances.find_one(name)
    paths = web_app.service.cache.paths_for_entity(instance, relative=True)
    return flask.jsonify([ str(item) for item in paths])

###
# Admin
###

# Same thing as login here, except we are only setting a new cookie
# for the access token.
@admin.route('/token/refresh', methods=['POST'])
@jwt_refresh_token_required
def admin_refresh():
    # Create the new access token
    current_user = get_jwt_identity()
    web_app=WebApplication.get()
    access_token = web_app.users.issue_access_token(current_user)

    # Set the JWT access cookie in the response
    resp = flask.jsonify({'refresh': True, **access_token})
    set_access_cookies(resp, access_token['access_token'])
    return resp, 200

# Use the set_access_cookie() and set_refresh_cookie() on a response
# object to set the JWTs in the response cookies. You can configure
# the cookie names and other settings via various app.config options
@admin.route('/token/auth', methods=['POST'])
def admin_login():
    log.info(f"[LOGIN] Received data: {flask.request.data}")
    username = flask.request.form.get('username', None)
    password = flask.request.form.get('password', None)
    if not username or not password:
        return flask.jsonify({'message': 'Username or password is missing'}), 401
    
    web_app=WebApplication.get()
    if not web_app.users.check_password(username, password):
        return flask.jsonify({'error': 'Invalid password'}), 401

    tokens = web_app.users.issue_tokens(username)

    # Set the JWT cookies in the response
    resp = flask.jsonify({'login': True, **tokens})
    set_access_cookies(resp, tokens.get('access_token'))
    set_refresh_cookies(resp, tokens.get('refresh_token'))
    return resp, 200

@admin.route('/login', methods=['GET'])
def admin_login_form():
    web_app = WebApplication.get()
    context = web_app.gen_context()
    return flask.render_template('admin/login.html', **context)


@admin.route('/index', methods=['GET'])
@jwt_required
def admin_index():
    web_app = WebApplication.get()
    user = get_jwt_identity()
    context = web_app.gen_context(user=user)
    return flask.render_template('admin/index.html', **context)

@admin.route('/token/valid', methods=['POST'])
@jwt_required
def admin_token_valid():
    web_app = WebApplication.get()
    user = get_jwt_identity()
    return flask.jsonify({'valid': True})

@admin.route('/cache-invalidate', methods=['POST'])
@jwt_required
def admin_cache_invalidate():
    web_app = WebApplication.get()
    items = web_app.service.cache.clear()
    return flask.jsonify({'message': "cache updated", "content": items})

register_blueprints(app)

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
