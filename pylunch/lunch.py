import logging
from typing import List, Optional, Mapping, Tuple, Union, Any, MutableMapping

import html2text
import requests
import yaml
import datetime
import collections.abc
from bs4 import BeautifulSoup, Tag
from requests import Response

from fuzzywuzzy import fuzz, process
from pathlib import Path

log = logging.getLogger(__name__)

RHLP_URL="http://rhlp-oskutka.8a09.starter-us-east-2.openshiftapps.com"

class LunchEntity:
    def __init__(self, config: Mapping[str, Any]):
        self._config = {**config}
        self.tags = tags or []

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
    def name(self) -> str:
        return self._config['name']

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
        return self._config.get('display_name') or self.name

    @property
    def tags(self) -> List[str]:
        return self._config.get('tags')

    def __str__(self) -> str:
        result = f"{self.__class__.__name__} \"{self.name}\""

        if self.display_name:
            result += f" ({self.display_name})"
        if self.tags:
            result += f" - {self.tags}"
        
        result += f" {self.url}"

        if self.selector:
            result += f" ({self.selector})"
        if self._request_params:
            result += f" - req_params={self._request_params}"
        return result

    def __repr__(self) -> str:
        return str(self)


class LunchResolver:
    def __init__(self, service: LunchService, entity: LunchEntity):
        self.service = service
        self.entity = entity

    def make_request(self, **kwargs) -> requests.Response:
        response = requests.get(self.entity.url, **kwargs)
        if not response.ok:
            log.warning(f"[LUNCH] Error[{response.status_code}]: {response.content}")
            print(f"Error[{response.status_code}]: ", response.content)
        return response

    def parse_response(self, response: Response) -> List[Tag]:
        soap = BeautifulSoup(response.content, "lxml")
        sub = soap.select(self.selector) if self.selector else soap
        return sub

    def invoke(self) -> str:
        response = self.make_request(**self._request_params)
        parsed = self.parse_response(response=response)
        log.info(f"[LUNCH] Parsed[{self.entity.name}]: {parsed}")
        string = self.to_string(parsed)
        return to_text(string)

    @classmethod
    def to_string(cls, parsed) -> str:
        if isinstance(parsed, list):
            items = [str(item) for item in parsed]
            log.debug(f">> String[{type(items)}]: {items}")
            return "".join(items)
        else:
            return parsed.extract()
    

class RHLPLunch(LunchEntity):
    def __init__(self, name: str, url: str = None, selector=None, request_params=None, **kwargs):
        url_name = url or name
        super().__init__(name, url=f"{RHLP_URL}/{url_name}", **kwargs)


class Resolvers:
    def __init__(self, **kwargs):
        self._collection = {**kwargs}
    
    def register(self, name: str, cls: type):
        log.info(f"[ADD] Resolver [{name}]: {cls.__name__}")
        self._collection[name] = cls

    def get(self, name: str) -> type:
        return self._collection.get(name, LunchResolver)

class Entities:
    def __init__(self):
        self._entities: MuttableMapping[str, LunchEntity] = {}

    @property
    def entities(self) -> MuttableMapping[str, LunchEntity]:
        return self._entities

    
    def get(self, name: str) -> Optional[LunchEntity]:
        if name in self.entities.keys():
            instance = self.instances[name]
            log.info(f"[LUNCH] Found in instances {name}: {instance}")
            return instance
        else:
            log.warning(f"[LUNCH] Not found in instances {name}")
            return None

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

    def register(self, name, url, display_name=None, tags=None, selector=None, request_params=None, **kwargs):
        config = dict(name=name, url=url, selector=selector, display_name=display_name, tags=tags, request_params=request_params, **kwargs)
        instance = LunchEntity(config)
        log.info(f"[REG] Register: {instance}")
        self.entities[name] = instance

class LunchService:
    def __init__(self, config_dir: Union[str, Path]):
        self._instances: Entities = Entities()
        self._resolvers: Resolvers = Resolvers(default=LunchResolver, rhlp=RHLPLunch)
        self._config_dir: Path = Path(config_dir) if config_dir is not None else None
        self.config: Optional[str, Any] = None
    
    @property
    def instances(self) -> Entities:
        return self._instances

    @property
    def restaurants_file(self) -> Path:
        return self.config_dir / 'restaurants.yaml'

    @property
    def config_file(self) -> Path:
        return self.config_dir / 'config.yaml'
    
    @property
    def config_dir(self) -> Mapping[str, Any]:
        return self._config_dir

    
    def import_file(self, file: Tuple[Path, str]):
        file = Path(file)
        if not file.exists():
            log.warning(f"[IMPORT] File not exists: {file}")
            return 
        with file.open("r") as fp:
            restaurants = yaml.safe_load(fp)
            for (name, restaurant) in restaurants['restaurants'].items():
                self.instances.register(**restaurant)
    
    def load_config(self, file: Path):
        file = Path(file)
        if not file.exists():
            log.warning(f"[LOAD] Config file not exists: {file}")
            return
        with file.open("r") as fp:
            self.config.update()
            

    def load(self):
        self.import_file(self.restaurants_file)
        self.load_config(self.config_file)    

    def save(self):
        if self.config_dir and not self.config_dir.exists():
            self.config_dir.mkdir(parents=True)

        with self.config_file.open("w") as fp:
            yaml.safe_dump(self.config, fp)

        with self.restaurants_file.open("w") as fp:
            data = dict()
            for (name, entity) in self.instances:
                yaml.safe_dump(dict(restaurants=data), fp)
                    
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

    def resolve(self, entity: LunchEntity) -> str:
        return entity.invoke()


class CachedLunchService(LunchService):
    def __init__(self, config_dir: Union[str, Path], cache_base=None):
        super().__init__(config_dir)
        self.cache_base = Path(cache_base) if cache_base else None
    
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

    def _entity_file(self, entity: LunchEntity) -> Path:
        if self.cache_base is None:
            return None
        return self._cache() / f"{entity.name}.lec"

    def resolve(self, entity: LunchEntity) -> str:
        file = self._entity_file(entity)
        if file is not None and file.exists():
            log.debug(f"[CACHE] Cache hit for {entity.name}: {file}")
            return file.read_text(encoding='utf-8')

        content = entity.invoke()
        if self.cache_base is not None:
            self._create_cache_for_day()
            log.debug(f"[CACHE] Writing \"{entity.name}\" to cache: {file}")
            file.write_text(content, encoding='utf-8')
        return content
               

def to_text(content):
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.ignore_tables = True
    h.ignore_emphasis = True
    return h.handle(str(content)).strip()
