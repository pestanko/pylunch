import logging
from typing import List, Optional, Mapping, Tuple, Union, Any, MutableMapping

import html2text
import requests
import yaml
import json
import datetime
import shutil
import collections
from bs4 import BeautifulSoup, Tag
from requests import Response
from pyzomato import Pyzomato

from fuzzywuzzy import fuzz, process
from pathlib import Path

from .tags_evaluator import TagsEvaluator
from .config import AppConfig, YamlLoader

log = logging.getLogger(__name__)


class LunchEntity(collections.MutableMapping):
    def __init__(self, config: Mapping[str, Any]):
        self._config = {**config}

    def __getitem__(self, k):
         return self._config.get(k)

    def __setitem__(self, k, v):
         self.config[k] = v
    
    def __delitem__(self, k):
         del self.config[k]
    
    def __iter__(self):
        return iter(self._config)
    
    def __len__(self):
         return len(self.config)

    @property
    def config(self) -> MutableMapping['str', Any]:
        return self._config

    @property
    def resolver(self) -> str:
        return self.config.get('resolver', 'default')

    @property
    def name(self) -> str:
        return self.config.get('name')

    @property
    def url(self) -> str:
        return self.config.get('url')

    @property
    def selector(self) -> str:
        return self.config.get('selector')

    @property
    def request_params(self) -> List:
        return self.config.get('request_params', {})

    @property
    def display_name(self) -> str:
        return self.config.get('display_name') or self.name

    @property
    def tags(self) -> List[str]:
        return self.config.get('tags')

    @property
    def disabled(self) -> bool:
        return self.config.get('disabled', False)

    def __str__(self) -> str:
        result = f"{self.__class__.__name__} \"{self.name}\""

        if self.display_name:
            result += f" ({self.display_name})"
        if self.tags:
            result += f" - {self.tags}"
        
        result += f" {self.url}"

        if self.selector:
            result += f" ({self.selector})"
        if self.request_params:
            result += f" - req_params={self.request_params}"
        return result

    def __repr__(self) -> str:
        return str(self.config)


class AbstractResolver:
    def __init__(self, service: 'LunchService', entity: LunchEntity):
        self.service = service
        self.entity = entity

    def resolve_text(self) -> str:
        return None

    def resolve_html(self) -> str:
        return None


class LunchResolver(AbstractResolver):
    @property
    def request_url(self) -> str:
        return self.entity.url

    def _make_request(self, **kwargs) -> requests.Response:
        response = requests.get(self.request_url, **kwargs)
        if not response.ok:
            log.warning(f"[LUNCH] Error[{response.status_code}]: {response.content}")
            print(f"Error[{response.status_code}]: ", response.content)
        else:
            log.debug(f"[RES] Response [{response.status_code}]: {response.content}")
        return response

    def _parse_response(self, response: Response) -> List[Tag]:
        soap = BeautifulSoup(response.content, "lxml")
        sub = soap.select(self.entity.selector) if self.entity.selector else soap
        log.info(f"[LUNCH] Parsed[{self.entity.name}]: {sub}")
        return sub

    def resolve_text(self) -> str:
        html_string = self.resolve_html()
        return to_text(html_string)

    def resolve_html(self) -> str:
        response = self._make_request(**(self.entity.request_params or {}))
        parsed = self._parse_response(response=response)
        return self.to_string(parsed)
        
    @classmethod
    def to_string(cls, parsed) -> str:
        if isinstance(parsed, list):
            items = [str(item) for item in parsed]
            return "".join(items)
        else:
            return parsed.extract()

class ZomatoResolver(AbstractResolver):
    @property
    def zomato(self) -> Pyzomato:
        return self.service.zomato

    def resolve_json(self):
        return self.zomato.getDailyMenu(self.entity.selector)
    
    def resolve_html(self) -> str:
        return f"<pre>{yaml.safe_dump(self.resolve_json())}</pre>"

    def resolve_text(self) -> str:
        result = ""
        content = self.resolve_json()
        menus = content['daily_menus']
        for menu in menus:
            menu = menu.get('daily_menu')
            dishes = menu['dishes']
            for dish in dishes:
                dish = dish['dish']
                result += f"{dish['name']} - {dish['price']}\n"
        return result

    
class LunchCollection(collections.MutableMapping):
    def __init__(self, cls_wrap=None, **kwargs):
        self._collection = { key: cls_wrap(val) if cls_wrap else val for (key, val) in kwargs.items() } 

    @property
    def collection(self) -> MutableMapping[str, Any]:
        return self._collection

    def __getitem__(self, k):
         return self.collection.get(k)
    def __setitem__(self, k, v):
         self.collection[k] = v
    def __delitem__(self, k):
         del self.collection[k]
    def __iter__(self):
        return iter(self.collection)
    def __len__(self):
         return len(self.collection) 

class Resolvers(LunchCollection):
    @property
    def collection(self) -> MutableMapping:
        return self._collection
    
    def register(self, name: str, cls: type):
        log.info(f"[ADD] Resolver [{name}]: {cls.__name__}")
        self._collection[name] = cls

    def get(self, name: str) -> type:
        return self._collection.get(name, LunchResolver)

    def for_entity(self, entity: LunchEntity) -> LunchResolver:
        return self.get(entity.resolver)


class Entities(LunchCollection):
    def __init__(self, **kwargs):
        super().__init__(cls_wrap=LunchEntity, **kwargs)
    @property
    def entities(self) -> MutableMapping[str, LunchEntity]:
        return self.collection

    def __getitem__(self, name) -> Optional[LunchEntity]:
        if name in self.entities.keys():
            instance = self.entities[name]
            log.info(f"[LUNCH] Found in entities {name}: {instance}")
            return instance
        else:
            log.warning(f"[LUNCH] Not found in entities {name}")
            return None

    def __setitem__(self, name, config):
        self.register(name=name, **config)

    def find_one(self, name: str):
        items = self._get_from_alias(name)
        if items:
            return self.get(items[0])
        return self.fuz_find_one(name)[0]

    def find_all(self, name: str, limit=10):
        return [i[0] for i in self.fuz_find(name, limit)]

    def fuz_find(self, name: str, limit=10) -> List[Tuple]:
        return process.extract(name, self.entities,
                               processor=lambda x: x if isinstance(x, str) else x.name,
                               scorer=fuzz.token_sort_ratio,
                               limit=limit)

    def fuz_find_one(self, name: str) -> Tuple:
        return process.extractOne(name, self.entities,
                                  processor=lambda x: x if isinstance(x, str) else x.name,
                                  scorer=fuzz.token_sort_ratio)

    def register(self, name: str, url: str, display_name: str=None, tags=None, 
                    selector=None, request_params=None, override=False, **kwargs):
        if name in self.entities.keys():
            if override:
                log.info(f"[REG] Overriding already existing: {name}")
            else:
                log.info(f"[REG] Skipping {name} since it already exists.")
                return
        config = dict(name=name, url=url, selector=selector, display_name=display_name, tags=tags, request_params=request_params, **kwargs)
        instance = LunchEntity(config)
        log.info(f"[REG] Register [{name}]: {instance}")
        self.entities[name] = instance

    def all_tags(self) -> List[str]:
        accumulator = set()
        for entity in self.entities.values():
            accumulator.update(entity.tags)
        return list(accumulator)
    
    def find_by_tags(self, expression: str):
        tags = TagsEvaluator(expression, self.all_tags())
        result = [ entity for entity in self.entities.values() if tags.evaluate(entity.tags) ]
        log.info(f"[FIND] Found by tags {expression}: {result}")
        return result

    def to_dict(self) -> dict:
        return { 'restaurants': { name: value.config for (name, value) in self.collection.items() } }
        

class LunchService:
    def __init__(self, config: AppConfig, entities: Entities):
        self._entities: Entities = entities
        self._resolvers: Resolvers = Resolvers(default=LunchResolver, zomato=ZomatoResolver)
        self._config: AppConfig = config
        self._zomato: Pyzomato = None

    @property
    def zomato(self) -> Pyzomato:
        if self._zomato is None:
            if self.config.zomato_key is None:
                return None
            self._zomato = Pyzomato(self.config.zomato_key)
        return self._zomato
    
    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def resolvers(self) -> Resolvers:
        return self._resolvers

    @property
    def instances(self) -> Entities:
        return self._entities
  
    def import_file(self, file: Tuple[Path, str], override=False):
        file = Path(file)
        if not file.exists():
            log.warning(f"[IMPORT] File not exists: {file}")
            return 
        with file.open("r") as fp:
            log.info(f"[IMPORT] Importing file: {file}")
            restaurants = yaml.safe_load(fp)
            for (name, restaurant) in restaurants['restaurants'].items():
                restaurant['name'] = name
                restaurant['override'] = override
                self.instances.register(**restaurant)  
                    
    def process_lunch_name(self, name: str) -> str:
        if not name or name == 'list':
            return self.to_string()
        log.info(f"[CMD] Lunch name: {name}")
        instance = self.instances.get(name)

        try:
            content = f"Restaurant: \"{name}\" - {instance.url}\n" + instance.invoke()
            log.debug(f"Content: {content}")
            return content
        except Exception as ex:
            return "ERR: {ex}"

    def __str__(self) -> str:
        return self.to_string()

    def to_string(self) -> str:
        result = "Available:\n"
        for restaurant in self.instances.values():
            result += f" - {restaurant.name} - {restaurant.url}\n"
        return result

    def resolve_text(self, entity: LunchEntity) -> str:
        resolver = self.resolvers.for_entity(entity)
        return resolver(self, entity).resolve_text()
    
    def resolve_html(self, entity: LunchEntity) -> str:
        resolver = self.resolvers.for_entity(entity)
        return resolver(self, entity).resolve_html()


class CachedLunchService(LunchService):
    def __init__(self, cfg: AppConfig, entities: Entities):
        super().__init__(cfg, entities)
        self.cache_base = Path(self.config.cache_dir)

    def resolve_text(self, entity: LunchEntity) -> str:
        return self._resolve_any(entity, super().resolve_text, ext='txt')

    def resolve_html(self, entity: LunchEntity) -> str:
        return self._resolve_any(entity, super().resolve_html, ext='html')

    def _resolve_any(self, entity: LunchEntity, func, ext: str = None):
        file = self._entity_file(entity, ext=ext)
        if file is not None and file.exists():
            log.debug(f"[CACHE] Cache hit for {entity.name}: {file}")
            return file.read_text(encoding='utf-8')

        content = func(entity)
        if self.cache_base is not None:
            self._create_cache_for_day()
            log.info(f"[CACHE] Writing \"{entity.name}\" to cache: {file}")
            file.write_text(str(content), encoding='utf-8')
        return content

    def _create_cache_for_day(self, day: str=None) -> Path:
        """
        Expected format: YYYY-MM-DD
        """
        if not self._cache().exists():
            self._cache().mkdir(parents=True)
        return self._cache

    @property
    def _today_date(self) -> str:
        return datetime.datetime.today().strftime('%Y-%m-%d')

    def _cache(self, date=None) -> Optional[Path]:
        if self.cache_base is None:
            return None
        return self.cache_base / (self._today_date if date is None else date)

    def _entity_file(self, entity: LunchEntity, ext=None) -> Path:
        ext = ext if ext is not None else 'txt'
        if self.cache_base is None:
            return None
        return self._cache() / f"{entity.name}.{ext}"

    def clear_cache(self):
        cache_dir = self._cache()
        log.info(f"Cleaning cache: {cache_dir}")
        shutil.rmtree(str(cache_dir), True)


def to_text(content):
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.ignore_tables = True
    h.ignore_emphasis = True
    return h.handle(str(content)).strip()
