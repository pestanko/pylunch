import logging
from typing import List, Optional, Tuple, Any, MutableMapping, Mapping, Union, Type, ValuesView, Dict

import html2text
import requests
import yaml
import json
import datetime
import shutil
import collections
import io
import os
import re
import unidecode
from bs4 import BeautifulSoup, Tag
from requests import Response
from pyzomato import Pyzomato

from fuzzywuzzy import fuzz, process
from pathlib import Path

from .tags_evaluator import TagsEvaluator
from .config import AppConfig
from pylunch import utils

from pdfminer import high_level
import pdfminer.layout

log = logging.getLogger(__name__)

USER_AGENTS = [
    # Chrome
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.90 Safari/537.36',
    'Mozilla/5.0 (Windows NT 5.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.90 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.2; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.90 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.133 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.133 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36',
    # Firefox
    'Mozilla/4.0 (compatible; MSIE 9.0; Windows NT 6.1)',
    'Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko',
    'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0)',
    'Mozilla/5.0 (Windows NT 6.1; Trident/7.0; rv:11.0) like Gecko',
    'Mozilla/5.0 (Windows NT 6.2; WOW64; Trident/7.0; rv:11.0) like Gecko',
    'Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko',
    'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.0; Trident/5.0)',
    'Mozilla/5.0 (Windows NT 6.3; WOW64; Trident/7.0; rv:11.0) like Gecko',
    'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64; Trident/7.0; rv:11.0) like Gecko',
    'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; WOW64; Trident/6.0)',
    'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/6.0)',
    'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; .NET CLR 2.0.50727; .NET CLR 3.0.4506.2152; .NET CLR 3.5.30729)'
]


class LunchEntity(collections.MutableMapping):
    def __init__(self, config: Mapping[str, Any]):
        self._config = {**config}
        self._logger = None

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

    @property
    def resolvers(self) -> List[MutableMapping]:
        return self.config.get('resolvers')

    @property
    def language(self) -> str:
        return self.config.get('language') or 'eng'

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
        if self.filters:
            result += f' filters={self.filters}'
        return result

    def __repr__(self) -> str:
        return str(self.config)

    @classmethod
    def clone(cls, origin: 'LunchEntity'):
        return cls(origin.config)


class ResolverConfig(collections.MutableMapping):
    def __init__(self, config: Mapping[str, Any], entity: LunchEntity = None, content=None):
        self._config = {**config}
        self._entity = entity
        self._content = content

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
    def entity(self) -> LunchEntity:
        return self._entity

    @property
    def name(self) -> str:
        return self.resolver

    @property
    def resolver(self) -> str:
        return self.config.get('resolver')

    @property
    def request_params(self) -> dict:
        return self.config.get('request_params', {})

    @property
    def url(self) -> str:
        return self.config.get('url')

    @property
    def selector(self) -> str:
        return self.config.get('selector') or self.entity.selector

    @property
    def content(self) -> str:
        return self._content if self._content is not None else self.config.get('content')

    @property
    def text(self) -> bool:
        text = self.config.get('text', 'false')
        from distutils import util
        return util.strtobool(text)

    @property
    def allow_cache(self) -> bool:
        return not self.no_cache

    @property
    def no_cache(self) -> bool:
        no_cache = self.config.get('no_cache', 'false')
        from distutils import util
        return util.strtobool(no_cache)


######
# Resolvers
######


class AbstractResolver:
    CACHE_EXT = 'txt'
    CACHE_SUFFIX = None
    CACHE_DISABLED = False

    def __init__(self, service: 'LunchService', config: ResolverConfig):
        self._service = service
        self._config = config
        self._log = self.service.log_factory.get_logger(self.config.entity.name)
        log.debug(f"[RESOLV] Instance of {self.__class__.__name__} with {config}")
        self._log.debug(f"[RESOLV] Instance of {self.__class__.__name__} with {config}")

    @property
    def config(self) -> ResolverConfig:
        return self._config

    @property
    def entity(self) -> LunchEntity:
        return self.config.entity

    @property
    def service(self) -> 'LunchService':
        return self._service

    def resolve(self, day=None, **kwargs) -> Any:
        cls = self.__class__
        log.info(f"[RESOLV] Resolving {self.entity.name} using the {cls.__name__}.")
        self._log.info(f"[RESOLV] Resolving {self.entity.name} using the {cls.__name__}.")
        try:
            suffix = cls.CACHE_SUFFIX or cls.__name__
            allow_cache = self.config.allow_cache and not cls.CACHE_DISABLED
            log.debug("[RESOLV] Cache state: {}")
            self._log.debug("[RESOLV] Cache state: {}")
            if allow_cache:
                return self.service.cache.wrap(entity=self.entity, func=self._resolve, day=day, ext=cls.CACHE_EXT,
                                               suffix=suffix)

            return self._resolve(day=day, **kwargs)
        except Exception as ex:
            log.error(f"[RESOLV] Resolved error {cls.__name__}: {ex}", exc_info=True)
            self._log.error(f"[RESOLV] Resolved error {cls.__name__}: {ex}", exc_info=True)
            return None

    def resolve_text(self, **kwargs) -> str:
        content = self.resolve(**kwargs)
        return None if not content else str(content)

    def _resolve(**kwargs) -> Any:
        """ This method should be overriden - abstract method
        """
        return None


class ResolverChain(AbstractResolver):
    CACHE_EXT = 'txt'
    CACHE_SUFFIX = 'chain'

    @property
    def chain(self) -> List[MutableMapping]:
        return self.entity.resolvers

    def _resolve(self, **kwargs) -> Any:
        content = None
        log.info(f"[CHAIN] Resolving chain for {self.entity.name}")
        for res_cfg in self.chain:
            config = ResolverConfig(config=res_cfg, entity=self.entity, content=content)
            resolved = self._resolve_one(config=config, content=content, **kwargs)

            if not resolved:
                log.warning(f"[CHAIN] Resolver {config.name} for {self.entity.name}: no content")
                self._log.warning(f"[CHAIN] Resolver {config.name} for {self.entity.name}: no content")
            else:
                log.info(f"[CHAIN] Resolver {config.name} for {self.entity.name}: {resolved}")
                self._log.info(f"[CHAIN] Resolver {config.name} for {self.entity.name}: {resolved}")
            content = resolved
        return content

    def _resolve_one(self, config, content, **kwargs):
        resolver = self.service.resolvers.get(config.name)
        if not resolver:
            log.warning(f"[CHAIN] Resolver {config.name} for {self.entity.name} was not found, skipping.")
            self._log.warning(f"[CHAIN] Resolver {config.name} for {self.entity.name} was not found, skipping.")
            return None
        self._log.info(f"[CHAIN] Using the resolver {config.name} for entity: {self.entity.name}: {resolver.__name__}")
        instance: AbstractResolver = resolver(service=self.service, config=config)
        if config.text:
            resolved = instance.resolve(**kwargs)
        else:
            resolved = instance.resolve_text(**kwargs)
        return resolved


class RequestResolver(AbstractResolver):
    CACHE_EXT = 'dat'
    CACHE_SUFFIX = 'raw-request'

    @classmethod
    def random_useragent(cls):
        import random
        return random.choice(USER_AGENTS)

    @property
    def request_url(self) -> str:
        return self.config.content or self.config.url or self.entity.url

    def get_request_params(self) -> dict:
        headers = {'User-Agent': self.__class__.random_useragent()}
        params = dict()
        if self.config.request_params:
            params.update(self.config.request_params)
            if 'headers' in params:
                params['headers'].update(headers)
        else:
            params['headers'] = headers
        return params

    def _resolve(self, **kwargs) -> Optional[requests.Response]:
        try:
            params = self.get_request_params()
            response = requests.get(self.request_url, **(params))
        except Exception as ex:
            log.error(f"Request error: {ex}")
            return None
        if not response.ok:
            log.warning(f"[LUNCH] Error[{response.status_code}] ({self.entity.name}): {response.content}")
            print(f"Error[{response.status_code}] {self.entity.name}: ", response.content)
        else:
            log.debug(f"[RES] Response [{response.status_code}] {self.entity.name}: {response.content}")
        return response

    def resolve_text(self, **kwargs) -> Optional[str]:
        res = self.resolve(**kwargs)
        if res.ok:
            return res.content.decode('utf-8')
        return None


class HtmlResolver(RequestResolver):
    CACHE_EXT = 'html'
    CACHE_SUFFIX = 'html'

    def _parse_response(self, response: Response) -> List[Tag]:
        soap = BeautifulSoup(response.content, "lxml")
        sub = soap.select(self.config.selector) if self.config.selector else soap
        log.debug(f"[LUNCH] Parsed[{self.entity.name}]: {sub}")
        return sub

    def resolve_text(self, **kwargs) -> Optional[str]:
        html_string = self.resolve(**kwargs)
        if html_string is None:
            return None
        return to_text(html_string)

    def _resolve(self, **kwargs) -> Optional[str]:
        response = super()._resolve(**kwargs)
        if response is None:
            return None
        parsed = self._parse_response(response=response)
        content = self.to_string(parsed)
        if not content:
            log.warning(f"[HTML] Content is empty for {self.entity.name} - {self.config.url} ({self.config.selector})")
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
            return str(parsed)


class AbstractHtmlResolver(AbstractResolver):
    CACHE_EXT = 'html'
    CACHE_SUFFIX = 'html'

    def resolve_text(self, **kwargs) -> Optional[str]:
        html_string = self.resolve(**kwargs)
        if html_string is None:
            return None
        return to_text(html_string)


class HtmlTagsSelectorResolver(AbstractHtmlResolver):
    CACHE_DISABLED = True

    def _resolve(self, **kwargs) -> List[Tag]:
        response: requests.Response = self.config.content

        soap = BeautifulSoup(response.content, "lxml")
        tags = soap.select(self.entity.selector) if self.entity.selector else soap
        log.debug(f"[LUNCH] Parsed[{self.entity.name}]: {tags}")
        return tags


class ToStringResolver(AbstractResolver):
    def _resolve(self, **kwargs) -> Optional[str]:
        string = self.config.content
        content = self.to_string(string)
        if not content:
            log.warning(f"[STR] Content is empty for {self.entity.name}")
            return None
        else:
            log.debug(f"[STR] Extracted content {self.entity.name}: {content}")
        return content

    @classmethod
    def to_string(cls, parsed) -> str:
        if isinstance(parsed, list):
            items = [str(item) for item in parsed]
            return "".join(items)
        else:
            return str(parsed.extract())


class HtmlTagsAttributeResolver(AbstractHtmlResolver):
    def _resolve(self, **kwargs):
        tags: List[Tag] = self.config.content

        return super()._resolve()


class ZomatoResolver(AbstractResolver):
    CACHE_EXT = 'json'
    CACHE_SUFFIX = 'zomato'
    ZOMATO_NOT_ENABLED = """
    Zomato key is not set, please get the zomato key and set add it to the configuration as property `zomato_key`.
    """

    @property
    def zomato(self) -> Pyzomato:
        return self.service.zomato

    def make_request(self) -> dict:
        return self.zomato.getDailyMenu(self.entity.selector)

    def _resolve(self, **kwargs) -> Optional[dict]:
        if self.zomato is None:
            return None
        content = self.make_request()
        log.debug(f"[ZOMATO] Response: {json.dumps(content, indent=2)}")
        return content

    def resolve_text(self, **kwargs) -> Optional[str]:
        content = self.resolve(**kwargs)
        if content is None:
            return None
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


class PDFResolver(RequestResolver):
    CACHE_EXT = 'pdf'
    CACHE_SUFFIX = 'pdf'

    def _resolve(self, **kwargs):
        response = super()._resolve(**kwargs)
        if not response or not response.ok:
            log.error(f"Unnable to get response from: {self.url}")
            return None
        text = self._resolve_text_from_content(io.BytesIO(response.content))
        log.info(f"[PDF] Resolved text: {text}")
        return text

    def resolve_text(self, **kwargs) -> str:
        text = self.resolve(**kwargs)
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


class OcrImgRawResolver(RequestResolver):
    CACHE_EXT = 'img'
    CACHE_SUFFIX = 'img-ocr'

    def _resolve(self, **kwargs):
        response = super()._resolve(**kwargs)
        if not response or not response.ok:
            log.error(f"Unnable to get response from: {self.url}")
            return None
        text = self._resolve_text_from_content(io.BytesIO(response.content))
        log.info(f"[IMG] Resolved image: {text}")
        return text

    def resolve_text(self, **kwargs) -> str:
        text = self.resolve(**kwargs)
        return f"PDF is available at: {self.entity.url}\n\n{text}"

    def _resolve_text_from_content(self, stream: io.BytesIO):
        import pytesseract
        from PIL import Image
        img = Image.open(stream)
        return pytesseract.image_to_string(img, lang=self.entity.language)


class OCRHeavyResolver(RequestResolver):
    CACHE_EXT = 'html'
    CACHE_SUFFIX = 'html-img'

    def _parse_response(self, response: Response) -> List[Tag]:
        soap = BeautifulSoup(response.content, "lxml")
        sub = soap.select(self.entity.selector) if self.entity.selector else soap
        log.debug(f"[LUNCH] Parsed[{self.entity.name}]: {sub}")
        return sub

    def _resolve(self, **kwargs) -> Optional[str]:
        response = super()._resolve(**kwargs)
        if response is None:
            return None
        parsed = self._parse_response(response=response)
        if not parsed:
            return None
        url = parsed[0]['src']
        log.info(f"[OCR] Got an URL for [{self.entity.name}]: {url}")
        config = ResolverConfig(entity=self.entity, config=self.entity.config, content=url)

        return OcrImgRawResolver(self.service, config=config).resolve(**kwargs)

    def resolve_text(self, **kwargs) -> Optional[Any]:
        html_string = self.resolve(**kwargs)
        if html_string is None:
            return None
        return html_string


######
# Filters
######

class LunchContentFilter:
    def __init__(self, service: 'LunchService', entity: LunchEntity):
        self.entity = entity
        self.service = service

    def filter(self, content: str, **kw) -> str:
        return content


class NewLinesFilter(LunchContentFilter):
    PATTERN = re.compile("(\n+)", flags=re.MULTILINE)

    def filter(self, content, **kwargs) -> str:
        content: str = super().filter(content)
        return self.__class__.PATTERN.sub("\n", content)


class CutFilter(LunchContentFilter):
    def _find_pos(self, content: str, sub: str, diacritics=False, shift: int = 0) -> Optional[int]:
        if sub is None or content is None:
            return None
        text = unidecode.unidecode(content) if not diacritics else content
        dec_sub = unidecode.unidecode(sub) if not diacritics else sub

        text = text if shift is None or shift == 0 or len(text) <= shift else text[shift:]

        log.debug(f"[CUT] Matching \"{dec_sub}\" in {text}, text-shift={shift}")
        pos: re.Match = re.search(dec_sub, text, re.IGNORECASE)
        if pos is None:
            log.warning(f"[CUT] Not found position of {sub} in the content for {self.entity.name}.")
            return None
        log.info(f"[CUT] Found for {self.entity.name} suitable day delimiter for {sub} at {pos}")
        return pos.start()

    def filter(self, content: str, cut_before=None, cut_after=None, diacritics=False, **kwargs) -> Optional[str]:
        if not content:
            return None

        beg_positions = self._filter_positions('cut_before', content=content, diacritics=diacritics)
        end_positions = self._filter_positions('cut_after', content=content, diacritics=diacritics)

        beg = 0 if not beg_positions else max(beg_positions)
        end = len(content) if not end_positions else min(end_positions)

        return content[beg:end]

    def _filter_positions(self, what, content: str, diacritics: bool=False):
        ent = self.entity.get(what)
        if ent is None:
            return None
        ents = [ent] if not isinstance(ent, list) else ent
        positions = [self._find_pos(content, pos, diacritics) for pos in ents]
        positions = [pos for pos in positions if pos != None]
        return positions


class DayResolveFilter(CutFilter):
    DAYS = [
        ['Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle'],
        ['Pondeli', 'Utery', 'Streda', 'Ctvrtek', 'Patek', 'Sobota', 'Nedele'],
        ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    ]

    @property
    def _week_day(self) -> int:
        return datetime.datetime.today().weekday()

    def options(self, day) -> Optional[List[Union[str, List[str]]]]:
        day = day
        opts = [self.entity.days] if self.entity.days is not None else []
        opts += self.__class__.DAYS
        res = [opt[day] for opt in opts if len(opt) > day]
        if not res:
            return None
        return res

    def find_day(self, day, content, diacritics=False, shift: int=0):
        if day is None or content is None:
            return None
        day_opts = self.options(day)
        if not day_opts:
            log.warning(f"[DAY] No suitable option for a day {day} for entity {self.entity.name}")
            return None
        for opt in day_opts:
            pos = self._find_pos(content, opt, diacritics=diacritics, shift=shift)
            if pos is not None:
                log.info(f"[DAY] Found for {self.entity.name} suitable day delimiter for a day {day}: {opt} at {pos}")
                return pos
        return None

    def filter(self, content, day_from=None, day_to=None, diacritics=False, **kwargs):
        if not content:
            return None

        day_from = day_from or self._week_day
        day_to = day_to or (day_from + 1)
        beg = self.find_day(day_from, content, diacritics=diacritics)
        shift = beg if beg is not None else 0
        end = self.find_day(day_to, content, diacritics=diacritics, shift=shift)
        if beg is None:
            beg = 0
        if end is None:
            end = len(content)

        end = end + shift

        return content[beg:end]


class LunchCollection(collections.MutableMapping):
    def __init__(self, cls_wrap=None, **kwargs):
        self._collection = {key: cls_wrap(val) if cls_wrap else val for (key, val) in kwargs.items()}

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
        if name is None or cls is None:
            return
        log.info(f"[ADD] Resolver [{name}]: {cls.__name__}")
        self._collection[name] = cls

    def get(self, name: str) -> type:
        return self._collection.get(name, HtmlResolver)

    def for_entity(self, entity: LunchEntity) -> Union[Type[ResolverChain], type]:
        if entity.resolvers is not None or entity.resolver == 'chain':
            log.info("[RESOLV] Using the chain resolver")
            return ResolverChain
        return self.get(entity.resolver)


class Filters(LunchCollection):
    def register(self, name: str, cls: type):
        log.info(f"[ADD] Filter [{name}]: {cls.__name__}")
        self._collection[name] = cls

    def get(self, name: str) -> type:
        return self._collection.get(name, LunchContentFilter)

    def for_entity(self, entity: LunchEntity) -> List[type]:
        log.debug(f"[FILTER] Filters for entity {entity.name} ~> {entity.filters}")
        return [self.get(flt) for flt in (entity.filters or [])]


class Entities(LunchCollection):
    def __init__(self, entities: dict, updated: datetime.datetime = None):
        super().__init__(cls_wrap=LunchEntity, **entities)
        self._updated = updated

    @property
    def collection(self) -> MutableMapping[str, Any]:
        if self._collection is None:
            self._collection = {}
        return self._collection

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
        if name is None:
            return
        self.register(name=name, **config)

    def find_one(self, name: str) -> LunchEntity:
        return self.get(name) or self.fuz_find_one(name)[0]

    def all(self) -> ValuesView:
        return self.values()

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

    def register(self, name: str, url: str, display_name: str = None, tags=None,
                 selector=None, request_params=None, override=False, **kwargs):
        if name is None:
            return
        if name in self.entities.keys():
            if override:
                log.info(f"[REG] Overriding already existing: {name}")
            else:
                log.info(f"[REG] Skipping {name} since it already exists.")
                return
        config = dict(name=name, url=url, selector=selector, display_name=display_name, tags=tags,
                      request_params=request_params, **kwargs)
        instance = LunchEntity(config)
        log.info(f"[REG] Register [{name}]: {instance}")
        self.entities[name] = instance

    def all_tags(self) -> List[str]:
        accumulator = set()
        for entity in self.entities.values():
            if entity.tags:
                accumulator.update(entity.tags)
        return list(accumulator)

    def find_by_tags(self, expression: str):
        tags = TagsEvaluator(expression, self.all_tags())
        result = [entity for entity in self.entities.values() if tags.evaluate(entity.tags)]
        log.info(f"[FIND] Found by tags {expression}: {result}")
        return result

    def to_dict(self) -> dict:
        return {
            'restaurants': {name: value.config for (name, value) in self.entities.items()},
            'timestamp': self._updated.isoformat() if self._updated is not None else None
            }

    def select(self, selectors, fuzzy=False, tags=False, with_disabled=True) -> List[LunchEntity]:
        def _get() -> List['LunchEntity']:
            if selectors is None or len(selectors) == 0:
                return list(self.values())
            if tags:
                full = " ".join(selectors)
                return self.find_by_tags(full)
            return [self.find_one(select) for select in selectors]

        instances = _get()
        instances = [instance for instance in instances if instance is not None]
        if with_disabled:
            return instances

        return [item for item in instances if item and not item.disabled]

    def select_as_dict(self, selectors, tags=False, with_disabled=True) -> Mapping:
        return {item.name: item for item in self.select(selectors, tags=tags, with_disabled=with_disabled) if item}


class RemoteSource(utils.CollectionWrapper):
    @property
    def config(self):
        return self.collection

    @property
    def url(self) -> str:
        return self.get('url')

    @property
    def name(self) -> str:
        return self.get('name')

    @property
    def disabled(self) -> bool:
        return self.get('disabled', False)

    @property
    def remote(self) -> bool:
        return self.get('remote', True)

class RemoteSources(utils.CollectionWrapper):
    def __init__(self, service: 'LunchService', **kwargs):
        super().__init__(cls_wrap=RemoteSource, **kwargs)
        self.service = service

    @property
    def sources(self) -> MutableMapping[str, RemoteSource]:
        return self.collection

    @property
    def enabled(self) -> List[RemoteSource]:
        return [item for item in self.sources.values() if not item.disabled]

    def import_sources(self):
        for source in self.enabled:
            self.import_source(source)

    def import_source(self, source: RemoteSource, override: False):
        if source.disabled:
            log.debug(f"Not importing disabled source - {source.name} ({source.url})")
            return False
        if source.url:
            self.service.import_url(source.url, override=override)
        return True

    def add(self, name: str, url: str, remote=True):
        self[name] = RemoteSource(name=name, url=url, remote=remote)
        return True


class LunchService:
    def __init__(self, config: AppConfig, entities: Entities):
        self._entities: Entities = entities
        self._resolvers: Resolvers = Resolvers(
            default=HtmlResolver,
            zomato=ZomatoResolver,
            ocr_img=OCRHeavyResolver,
            ocr_raw=OcrImgRawResolver,
            pdf=PDFResolver,
            request=RequestResolver,
            chain=ResolverChain,
            html_tags=HtmlTagsSelectorResolver,
            html=HtmlResolver,
            html_attr=HtmlTagsAttributeResolver
        )
        self._filters: Filters = Filters(
            raw=LunchContentFilter,
            day=DayResolveFilter,
            nl=NewLinesFilter,
            cut=CutFilter
        )
        self._config: AppConfig = config
        self._zomato: Optional[Pyzomato] = None
        self._cache: LunchCache = LunchCache(self)
        self._blacklist: EntityBlacklist = EntityBlacklist(self)
        self._sources = RemoteSources(self)
        self._log_factory = LunchLoggerFactory(self.cache)

    @property
    def log_factory(self) -> 'LunchLoggerFactory':
        return self._log_factory

    @property
    def cache(self) -> 'LunchCache':
        return self._cache

    @property
    def blacklist(self) -> 'EntityBlacklist':
        return self._blacklist

    @property
    def zomato(self) -> Optional[Pyzomato]:
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
            self._import_restaurants(restaurants, override=override)

    def import_string(self, string: str, override=False):
        log.info(f"[IMPORT] Importing content: {string}")
        restaurants = yaml.safe_load(string)
        self._import_restaurants(restaurants, override=override)

    def import_url(self, url: str, override=False):
        res = requests.get(url=url)
        if not res.ok:
            log.error(f"[IMPORT] Unable to get from \"{url}\"[{res.status_code}]: {res.content}")
            return
        self.import_string(res.content, override=override)

    def _import_restaurants(self, restaurants, override=False):
        for (name, restaurant) in restaurants['restaurants'].items():
            restaurant['name'] = name
            restaurant['override'] = override
            if restaurant.get('tags') and restaurant.get('resolver', 'default') != 'default' \
                    and restaurant['resolver'] not in restaurant['tags']:
                restaurant['tags'].append(restaurant['resolver'])
            log.info(f"[IMP] Importing restaurant: {restaurant}")
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

    def resolve_text(self, entity: LunchEntity, **kwargs) -> str:
        return self.cache.wrap(entity, func=self._resolve_text, ext='txt', **kwargs)

    def _resolve(self, entity, **kwargs):
        if entity.disabled:
            return None

        content = self._get_resolver(entity).resolve(**kwargs)

        if not content:
            log.warning(f"[SERVICE] No content for {entity.name}")
            return None
        return content

    def resolve(self, entity, **kwargs):
        return self._cache_wrap(entity, func=self._resolve, ext='cache', **kwargs)

    def _resolve_text(self, entity: LunchEntity, **kwargs) -> Union[Optional[str], Any]:
        if entity.disabled:
            return None

        content = self._get_resolver(entity).resolve_text(**kwargs)
        if not content:
            log.warning(f"[SERVICE] No content for {entity.name}")
            return None

        # Do not apply filters if no filters
        content = content if kwargs.get('no_filters') else self._apply_filters(entity, content, **kwargs)
        return content.strip()

    def _get_resolver(self, entity) -> AbstractResolver:
        resolver = self.resolvers.for_entity(entity)
        log.debug(f"[RESOLVER] Using the resolver for {entity.name}: {resolver.__name__}")
        config = ResolverConfig(config=entity.config, entity=entity, content=None)

        return resolver(service=self, config=config)

    def _apply_filters(self, entity: 'LunchEntity', content: str, **kwargs):
        filters = self.filters.for_entity(entity)
        for flt in filters:
            if flt == DayResolveFilter and kwargs.get('full'):
                log.info("[FILTER] Skip the 'day' filter since full content expected.")
                continue
            log.debug(f"[FILTER] Using the text filter: {flt.__name__}")
            content = flt(self, entity).filter(content)
        return content


class EntityBlacklist:
    def __init__(self, service: LunchService):
        self._service = service

    @property
    def service(self) -> LunchService:
        return self._service

    def load(self) -> MutableMapping:
        if not self.path.exists():
            return {}
        return json.load(self.path.open('r'))

    def save(self, blacklist: MutableMapping):
        parent: Path = self.path.parent
        if not parent.exists():
            parent.mkdir(parents=True)
        json.dump(blacklist, self.path.open('w'))

    @property
    def path(self) -> Path:
        return self.service.cache.cache_base / self.service.cache.for_day(day=None) / 'blacklist.json'

    def get(self, entity: LunchEntity = None) -> Optional[Dict]:
        if self.service.cache.disabled:
            return None

        blacklist = self.load()
        return blacklist.get(entity.name)

    def is_blacklisted(self, entity: LunchEntity) -> bool:
        metadata = self.get(entity)
        return self.metadata_blacklisted(metadata)

    def metadata_blacklisted(self, metadata: MutableMapping) -> bool:
        if not metadata:
            return False
        now = datetime.datetime.now()
        meta_time = datetime.datetime.fromtimestamp(metadata['timestamp'])
        return meta_time > now

    def blacklist(self, entity: LunchEntity):
        name = entity.name
        if self.service.cache.disabled:
            log.info("[BLKL] Cache is disabled - not blacklisting")
            return False
        blacklist = self.load()

        if blacklist is None:
            return False

        if name not in blacklist.keys():
            log.info(f"[BLKL] Entity {name} not found in the blacklist!")
            base = dict(name=name, count=1)
            blacklist[name] = base
        else:
            log.info(
                f"[BLKL] Entity {name} found in the blacklist - increasing the count {blacklist[name]['count'] + 1}")
            blacklist[name]['count'] += 1

        black_time = datetime.datetime.now() + datetime.timedelta(minutes=15)
        blacklist[name]['timestamp'] = black_time.timestamp()

        self.save(blacklist)
        return True

    def whitelist(self, entity: LunchEntity):
        name = entity.name
        if self.service.cache.disabled:
            log.info("[BLKL] Cache is disabled - not blacklisting")
            return False

        blacklist = self.load()

        if blacklist is None:
            return False

        if name not in blacklist:
            log.info(f"[BLKL] Entity {name} not found in the blacklist!")
            return False

        del blacklist[name]

        self.save(blacklist)


class LunchCache:
    def __init__(self, service: 'LunchService'):
        self.service = service
        log.info(f"[CACHE] Using cache: {self.cache_base}")

    @property
    def config(self) -> AppConfig:
        return self.service.config

    @property
    def enabled(self) -> bool:
        return not self.disabled

    @property
    def disabled(self) -> bool:
        return self.config.get('no_cache', False) or self.cache_base is None

    @property
    def cache_base(self) -> Path:
        return Path(self.config.cache_dir)

    def save(self, path: Path, content: str):
        if self.disabled:
            log.info(f"[CACHE] Cache is not enabled or cache dir not set - not saving")
            return

        if content is None:
            log.warning(f"[CACHE] No content provided - not saving: {path}")

        log.info(f"[CACHE] Writing content to cache: {path}")
        fp: Path = self._cache_path(path)
        self._create_dir(fp.parent)
        fp.write_text(str(content), encoding='utf-8')

    def get(self, path: Path) -> Optional[str]:
        return self.file_content(path)


    def file_content(self, file: str) -> str:
        if self.disabled:
            log.debug(f"[CACHE] Cache is not enabled or cache dir not set - no content")
            return None

        fp = Path(file)
        fp = fp if fp.is_absolute() else self._cache_path(file)

        if not fp.exists():
            log.warning(f"[CACHE] Cache for item not exists: {fp}")
            return None

        if not utils.is_forward_path(self.cache_base, file):
            log.error(f"[CACHE] Cache path is not forward item not exists: {fp}")
            return None

        return fp.read_text(encoding='utf-8')


    def _cache_path(self, fragment: Path) -> Path:
        fragment = Path(fragment)
        fp = self.cache_base / fragment
        return fp.resolve()

    def cache_path(self, fragment: Path) -> Path:
        fp =  self._cache_path(fragment)
        self._create_dir(fp.parent)
        return fp

    def _create_dir(self, dir: Path) -> Path:
        dir = Path(dir)
        if not dir.exists():
            dir.mkdir(parents=True)
        return dir

    @property
    def _today_date(self) -> str:
        return datetime.datetime.today().strftime('%Y-%m-%d')

    def _cache(self, date=None) -> Optional[Path]:
        if self.cache_base is None:
            return None
        return Path(self._today_date if date is None else date)

    def for_day(self, day: str = None) -> Path:
        if day is None:
            day = self._today_date
        return Path(day)

    def create_fragment(self, entity: LunchEntity, day=None, suffix=None, ext='txt') -> Path:
        file_name = entity.name
        if suffix is not None:
            file_name += "-" + suffix
        return self.for_day(day) / f'{file_name}.{ext}'

    def store_entity(self, entity: LunchEntity, content: str, suffix=None, day=None, ext='txt'):
        fragment = self.create_fragment(entity, day=day, suffix=None, ext=ext)
        self.save(fragment, content)

    def get_entity(self, entity: LunchEntity, day=None, suffix=None, ext='txt'):
        if self.disabled:
            log.info("[CACHE] Cache is not enabled.")
            return None
        fragment = self.create_fragment(entity, day=day, suffix=suffix, ext=ext)
        log.info(f"[CACHE] Cache for entity {entity.name}: {fragment}")
        content = self.get(fragment)
        if not content:
            log.debug(f"[CACHE] No content for {entity.name} - {fragment}")
        return content if content else None

    def paths_for_entity(self, entity: LunchEntity, day=None, relative=False):
        if self.disabled:
            log.info("[CACHE] Cache is not enabled.")
            return None

        dir = self.for_day(day)
        fdir = self.cache_base / dir
        paths = list(fdir.glob(f"{entity.name}*"))
        if paths and relative:
            paths = [path.relative_to(self.cache_base) for path in paths]
        return paths

    def clear(self, instances=None, day=None):
        if self.disabled:
            log.info("[CACHE] Cache is not enabled.")
            return

        if instances is None:
            dir = str(self._cache_path(self.for_day(day)))
            log.info(f"[CACHE] Removing the directory: {dir}")
            shutil.rmtree(dir, ignore_errors=True)
            return [dir]

        result = []
        for inst in instances:
            files = self.paths_for_entity(inst, day=day)
            self.service.blacklist.whitelist(inst)
            for file in files:
                result.append(str(file))
                file.unlink()
        return result

    def wrap(self, entity: LunchEntity, func, day=None, ext=None, suffix=None, **kwargs) -> str:
        if not self.enabled:
            return self._execute_func(entity=entity, func=func, **kwargs)

        cached = self.get_entity(entity, day=day, ext=ext, suffix=suffix)
        if cached:
            return cached

        content = self._execute_func(entity=entity, func=func, **kwargs)
        if content:
            self.store_entity(entity, content=content, ext=ext, suffix=suffix)
        return content

    def _execute_func(self, entity: LunchEntity, func, **kwargs):
        metadata = self.service.blacklist.get(entity)
        if metadata and self.service.blacklist.metadata_blacklisted(metadata):
            log.debug(
                f"[CACHE] Entity {entity.name} is blaclisted until {datetime.datetime.fromtimestamp(metadata['timestamp'])}.")
            return None
        result = func(entity=entity, **kwargs)
        if not result:
            log.info(f"[CACHE] Blaclisting {entity.name} for 15 minutes.")
            self.service.blacklist.blacklist(entity)
        return result

    def content(self, day=None):
        if self.disabled:
            return None

        day_path = self.for_day(day=day)
        log.info(f"[CACHE] Cache content for {day_path}: {self.cache_base / day_path}")
        full = str(self.cache_base / day_path)
        return list(os.listdir(full))


class LunchLoggerFactory:
    def __init__(self, cache: 'LunchCache'):
        self._cache = cache
        self._loggers = {}

    def get_logger(self, name: str) -> logging.Logger:
        if name in self._loggers:
            return self._loggers[name]
        logger = self.create_logger(name)
        self._loggers[name] = logger
        return logger

    def create_logger(self, name:str) -> logging.Logger:
        logger = logging.getLogger(f"_ent_{name}")
        formatter = logging.Formatter('%(levelname)s %(asctime)s - %(module)s: %(message)s')
        if self._cache.enabled:
            fd = self._cache.cache_path(f"{name}.log")
            handler = logging.FileHandler(str(fd))
        else:
            handler = logging.StreamHandler()

        handler.setLevel(logging.DEBUG)

        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger


def to_text(content):
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.ignore_tables = True
    h.ignore_emphasis = True
    return h.handle(str(content)).strip()
