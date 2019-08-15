import logging
from typing import List, Optional, Mapping, Tuple, Union, Any, MutableMapping, Mapping

import html2text
import requests
import yaml
import json
import datetime
import shutil
import collections
import io
import re
import locale
from bs4 import BeautifulSoup, Tag
from requests import Response
from pyzomato import Pyzomato

from fuzzywuzzy import fuzz, process
from pathlib import Path

from .tags_evaluator import TagsEvaluator
from .config import AppConfig, YamlLoader

from pdfminer import high_level
import pdfminer.layout

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

    @property
    def days(self) -> List[str]:
        return self.config.get('days')

    @property
    def filters(self) -> str:
        return self.config.get('filters')

    def __str__(self) -> str:
        result = f"\"{self.name}\" -"

        if self.display_name:
            result += f" ({self.display_name})"
        if self.tags:
            result += f" {self.tags}"
        
        result += f" {self.url}"

        if self.selector:
            result += f" ({self.selector})"
        if self.request_params:
            result += f" - req_params={self.request_params}"

        if self.resolver and self.resolver != 'default':
            result += f' resolver={self.resolver}'
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

class LunchContentFilter:
    def __init__(self, service: 'LunchService', entity: LunchEntity):
        self.entity = entity
        self.service = service

    def filter(self, content: str) -> str:
        return content

class DayResolveFilter:
    CZ_DAYS = ['Pondelí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle']
    EN_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def __init__(self, service: 'LunchService', entity: LunchEntity):
        self.entity = entity
        self.service = service

    @property
    def _week_day(self) -> int:
        return datetime.datetime.today().weekday()

    def _find_pos_content(self, day_num, content, days):
        if day_num >= len(days):
            log.warning(f"Week day \"{day_num}\" is greater than available days {len(days)}")
            return None

        day = days[day_num]
        found = re.search(day, content, re.IGNORECASE)
        if not found:
            log.warning(f"Day \"{day}\" was not found in the content")
            fallback = self._find_pos_content(day_num, content, self.__class__.EN_DAYS)
            if fallback:
                log.info(f"Fallback option has been found: {fallback} position")
                return fallback
            else:
                log.warning(f"Fallback failed for {self.entity.name} and day number {day_num}.")
                return None
        return found.start()
        

    def _parse_by_day(self, content: str, days: List[str]) -> str:
        if not days:
            log.debug("[FILTER] No days selected - sending original content")
            return content
        start = self._find_pos_content(self._week_day, content, days)
        if start is None:
            log.warning("[FILTER] Unable to find begging of the day, sending original conent")
            return content
        end = self._find_pos_content(self._week_day + 1, content, days)
        if end is None:
            log.debug(f"[FILTER] Sending content from {start} to the end of the document.")
            return content[start:]
        log.debug(f"[FILTER] Sending content from {start} to {end}.")
        return content[start:end]


    def _select_correct_days(self, content: str):
        days = self.entity.days
        if days:
            return days
        
        today_num = self._week_day
        options = [self.__class__.CZ_DAYS, self.__class__.EN_DAYS]
        for option in options:
            if re.search(option[today_num], content, re.IGNORECASE):
                log.debug(f"[DAYS] Selecting correct days for [{option[today_num]}]: {option}")
                return option
        return None

    def filter(self, content: str):
        days = self._select_correct_days(content)
        result = self._parse_by_day(content, days)
        return result


class LunchResolver(AbstractResolver):
    @property
    def request_url(self) -> str:
        return self.entity.url

    def _make_request(self, **kwargs) -> requests.Response:
        response = requests.get(self.request_url, **kwargs)
        if not response.ok:
            log.warning(f"[LUNCH] Error[{response.status_code}] ({self.entity.name}): {response.content}")
            print(f"Error[{response.status_code}] {self.entity.name}: ", response.content)
        else:
            log.debug(f"[RES] Response [{response.status_code}] {self.entity.name}: {response.content}")
        return response

    def _parse_response(self, response: Response) -> List[Tag]:
        soap = BeautifulSoup(response.content, "lxml")
        sub = soap.select(self.entity.selector) if self.entity.selector else soap
        log.info(f"[LUNCH] Parsed[{self.entity.name}]: {sub}")
        return sub

    def resolve_text(self) -> str:
        html_string = self.resolve_html()
        if html_string is None:
            return None
        return to_text(html_string)

    def resolve_html(self) -> str:
        response = self._make_request(**(self.entity.request_params or {}))
        parsed = self._parse_response(response=response)
        content = self.to_string(parsed)
        if not content:
            log.warning(f"[HTML] Content is empty for {self.entity.name} - {self.entity.url} ({self.entity.selector})")
            return None
        else:
            log.debug(f"[HTML] Extracted content {self.entity.name}: {content}")
        return content 
        
    @classmethod
    def to_string(cls, parsed) -> str:
        if isinstance(parsed, list):
            items = [str(item) for item in parsed]
            return "".join(items)
        else:
            return str(parsed.extract())


class ZomatoResolver(AbstractResolver):
    ZOMATO_NOT_ENABLED="""Zomato key is not set, please get the zomato key 
                        and set add it to the configuration as property `zomato_key`."""
    @property
    def zomato(self) -> Pyzomato:
        return self.service.zomato

    def resolve_json(self):
        if self.zomato is None:
            return None
        content = self.zomato.getDailyMenu(self.entity.selector)
        log.info(f"[ZOMATO] Response: {json.dumps(content, indent=2)}")
        return content
    
    def resolve_html(self) -> str:
        resolved = self.resolve_json()
        if resolved is None:
            return f"<p>{ZomatoResolver.ZOMATO_NOT_ENABLED}</p>"
        result = "<div>\n"
        lines = self._make_lines(resolved)
        for line in lines:
            result += f"<p>{line}</p>\n"
        return result + "\n</div>"

    def resolve_text(self) -> str:
        content = self.resolve_json()
        if content is None:
            return ZomatoResolver.ZOMATO_NOT_ENABLED
        return "\n".join(self._make_lines(content))

    def _make_lines(self, content: dict) -> list:
        result = []
        menus = content['daily_menus']
        for menu in menus:
            menu = menu.get('daily_menu')
            dishes = menu['dishes']
            for dish in dishes:
                dish = dish['dish']
                result.append(f"{dish['name']} - {dish['price']}")
        return result


class PDFResolver(AbstractResolver):
    def resolve_pdf(self):
        response = requests.get(self.entity.url)
        if not response.ok:
            log.error(f"Unnable to get response from: {self.url}")
            return None
        text = self._resolve_text_from_content(io.BytesIO(response.content))
        log.info(f"[PDF] Resolved text: {text}")
        return text
    
    def resolve_html(self) -> str:
        result = "<div>\n"
        result += f'<a href="{self.entity.url}">{self.entity.display_name}<a>'
        return result + "\n</div>"

    def resolve_text(self) -> str:
        text = self.resolve_pdf()
        return f"PDF is available at: {self.entity.url}\n\n{text}" 

    def _resolve_text_from_content(self, stream: io.BytesIO):
        out = io.BytesIO()
        laparams = pdfminer.layout.LAParams()
        for param in ("all_texts", "detect_vertical", "word_margin", "char_margin", "line_margin", "boxes_flow"):
            paramv = locals().get(param, None)
            if paramv is not None:
                setattr(laparams, param, paramv)

        high_level.extract_text_to_fp(stream, outfp=out, laparams=laparams)
        return out.getvalue().decode('utf-8')

    
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
    def register(self, name: str, cls: type):
        log.info(f"[ADD] Resolver [{name}]: {cls.__name__}")
        self._collection[name] = cls

    def get(self, name: str) -> type:
        return self._collection.get(name, LunchResolver)

    def for_entity(self, entity: LunchEntity) -> LunchResolver:
        return self.get(entity.resolver)

class Filters(LunchCollection):
    def register(self, name: str, cls: type):
        log.info(f"[ADD] Filter [{name}]: {cls.__name__}")
        self._collection[name] = cls

    def get(self, name: str) -> type:
        return self._collection.get(name, LunchContentFilter)

    def for_entity(self, entity: LunchEntity) -> LunchContentFilter:
        log.debug(f"[FILTER] Filters for entity {entity.name} ~> {entity.filters}")
        return [ self.get(flt) for flt in (entity.filters or []) ]


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
        return self.get(name) or self.fuz_find_one(name)[0]

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
            accumulator.update(entity.tags if entity.tags else {})
        return list(accumulator)
    
    def find_by_tags(self, expression: str):
        tags = TagsEvaluator(expression, self.all_tags())
        result = [ entity for entity in self.entities.values() if tags.evaluate(entity.tags) ]
        log.info(f"[FIND] Found by tags {expression}: {result}")
        return result

    def to_dict(self) -> dict:
        return { 'restaurants': { name: value.config for (name, value) in self.collection.items() } }

    def select(self, selectors, fuzzy=False, tags=False, with_disabled=True) -> List[LunchEntity]:
        def _get() -> List['lunch.LunchEntity']:
            if selectors is None or len(selectors) == 0:
                return list(self.values())
            if tags:
                full = " ".join(selectors)
                return self.find_by_tags(full)
            if fuzzy:
                return [ self.fuz_find_one(select) for select in selectors ]
            return [ self.find_one(select) for select in selectors ]

        instances = _get()
        instances = [instance for instance in instances if instance is not None]
        if with_disabled:
            return instances

        return [ item for item in instances if item and not item.disabled]
        

class LunchService:
    def __init__(self, config: AppConfig, entities: Entities):
        self._entities: Entities = entities
        self._resolvers: Resolvers = Resolvers(default=LunchResolver, zomato=ZomatoResolver, pdf=PDFResolver)
        self._filters: Filters = Filters(raw=LunchContentFilter, day=DayResolveFilter)
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
    def filters(self) -> Filters:
        return self._filters

    @property
    def instances(self) -> Entities:
        return self._entities
  
    def import_file(self, file: Tuple[Path, str], override=False):
        file = Path(file)
        if not file.exists():
            log.warning(f"[IMPORT] File not exists: {file}")
            return 
        with file.open("r", encoding='utf-8') as fp:
            log.info(f"[IMPORT] Importing file: {file}")
            restaurants = yaml.safe_load(fp)
            for (name, restaurant) in restaurants['restaurants'].items():
                restaurant['name'] = name
                restaurant['override'] = override
                if restaurant.get('tags') and restaurant.get('resolver', 'default') != 'default' and restaurant['resolver'] not in restaurant['tags']:
                    restaurant['tags'].append(restaurant['resolver'])
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
        result = f"Available ({len(self.instances)}): \n"
        for restaurant in self.instances.values():
            result += f" - {restaurant.name} - {restaurant.url}\n"
        return result

    def resolve_text(self, entity: LunchEntity) -> str:
        resolver = self.resolvers.for_entity(entity)
        log.debug(f"[RESOLVER] Using the resolver: {resolver.__name__}")
        content = resolver(self, entity).resolve_text()
        if not content:
            log.warning(f"[SERVICE] No content for {entity.name}")
            return None
        filters = self.filters.for_entity(entity)
        for flt in filters:
            log.debug(f"[FILTER] Using the text filter: {flt.__name__}")
            content = flt(self, entity).filter(content)
        return content
    
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
        if not content:
            log.warning(f"[CACHE] No content provided for {entity.name}")
            return f'No content provided for {entity} - not caching'
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

    def clear_cache(self, lst: List[LunchEntity] = None, full=False):
        cache_dir = self._cache() if not full else self.cache_base
        if not lst:
            log.info(f"Cleaning cache: {cache_dir}")
            shutil.rmtree(str(cache_dir), True)
            return [cache_dir]
        else:
            return self._clear_items(cache_dir, lst)
    
    def _clear_items(self, base_dir, lst) -> List:
        result = []
        for item in lst:
            paths: List[Path] = base_dir.glob(f"{item.name}.*")
            for path in paths:
                log.info(f"[CACHE] Removing {item.name}: {path}")
                path.unlink()
                result.append(path)
        return result

    def cache_content(self, lst: List[LunchEntity] = None) -> Mapping:
        base = self._cache()
        log.debug(f"[CACHE] Base: {base}")
        result =  { name: list(str(pth) for pth in base.glob(f'{entity.name}.*')) for (name, entity) in self.instances.items() }
        log.debug(f"[CACHE] Content: {result}")
        return result
        


def to_text(content):
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.ignore_tables = True
    h.ignore_emphasis = True
    return h.handle(str(content)).strip()
