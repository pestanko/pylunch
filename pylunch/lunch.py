import logging
from typing import List, Optional, Mapping, Tuple

import html2text
import requests
import yaml
import datetime
from bs4 import BeautifulSoup, Tag
from requests import Response

from fuzzywuzzy import fuzz, process
from pathlib import Path

log = logging.getLogger(__name__)

RHLP_URL="http://rhlp-oskutka.8a09.starter-us-east-2.openshiftapps.com"

class LunchEntity:
    def __init__(self, name: str, url: str=None, display_name: str=None, tags: List[str]=None, selector: str=None, request_params: List[str]=None):
        self._name = name
        self._url = url
        self._selector = selector
        self._request_params = request_params or {}
        self._display_name = display_name
        self.tags = tags or []

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return self._display_name or self.name

    @property
    def url(self) -> str:
        return self._url

    def make_request(self, **kwargs) -> requests.Response:
        response = requests.get(self._url, **kwargs)
        if not response.ok:
            log.warning(f"[LUNCH] Error: {response.content}")
        return response

    def get_soap(self, response: Response) -> BeautifulSoup:
        soup = BeautifulSoup(response.content, "lxml")
        return soup

    def parse(self, response: Response) -> List[Tag]:
        soap = self.get_soap(response)
        sub = soap.select(self._selector) if self._selector else soap
        return sub

    def invoke(self) -> str:
        response = self.make_request(**self._request_params)
        parsed = self.parse(response=response)
        log.info(f"[LUNCH] Parsed[{self._name}]: {parsed}")
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

    def __str__(self) -> str:
        result = f"{self.__class__.__name__} \"{self._name}\""

        if self.display_name:
            result += f" ({self.display_name})"
        if self.tags:
            result += f" - {self.tags}"
        
        result += f" {self._url}"

        if self._selector:
            result += f" ({self._selector})"
        if self._request_params:
            result += f" - req_params={self._request_params}"
        return result

    def __repr__(self) -> str:
        return str(self)


class RHLPLunch(LunchEntity):
    def __init__(self, name: str, url: str = None, selector=None, request_params=None, **kwargs):
        url_name = url or name
        super().__init__(name, url=f"{RHLP_URL}/{url_name}", **kwargs)


class LunchService:
    def __init__(self):
        self._instances: Mapping[str, LunchEntity] = {}
        self._providers: Mapping[str, type] = dict(default=LunchEntity, rhlp=RHLPLunch)
    
    @property
    def instances(self) -> Mapping[str, LunchEntity]:
        return self._instances

    @property
    def register_provider(self, name: str, cls: type):
        log.info(f"[ADD] Provider [{name}]: {cls.__name__}")
        self._providers[name] = cls

    def get(self, name: str) -> Optional[LunchEntity]:
        if name in self.instances.keys():
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
        return process.extract(name, self.instances,
                               processor=lambda x: x if isinstance(x, str) else x.name,
                               scorer=fuzz.token_sort_ratio,
                               limit=limit)

    def fuz_find_one(self, name: str) -> Tuple:
        return process.extractOne(name, self.instances,
                                  processor=lambda x: x if isinstance(x, str) else x.name,
                                  scorer=fuzz.token_sort_ratio)

    def register(self, name, url, display_name=None, tags=None, selector=None, request_params=None, cls=LunchEntity):
        instance = cls(name=name, url=url, selector=selector, display_name=display_name, tags=tags, request_params=request_params)
        log.info(f"[REG] Register: {instance}")
        self.instances[name] = instance

    
    def register_from_file(self, file: Tuple[Path, str]):
        file = Path(file)
        with file.open("r") as fp:
            restaurants = yaml.safe_load(fp)
            for (name, restaurant) in restaurants['restaurants'].items():
                self.instances[name] = self.create_restaurant(name, restaurant)

    def create_restaurant(self, name: str, restaurant: dict) -> LunchEntity:
        cls_name = 'default'
        if 'cls' in restaurant:
            cls_name = restaurant['cls']
            del restaurant['cls']
        cls = self._get_provider(cls_name)
        restaurant['name'] = name
        return cls(**restaurant)
                    
    def process_lunch_name(self, name: str) -> str:
        if not name or name == 'list':
            return self.to_string()
        log.info(f"[CMD] Lunch name: {name}")
        instance = get(name)

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


    def _get_provider(self, name: str) -> type:
        return self._providers.get(name) or self._providers['default']


class CachedLunchService(LunchService):
    def __init__(self, cache_base=None):
        super().__init__()
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
