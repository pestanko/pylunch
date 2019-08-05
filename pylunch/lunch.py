import logging
from typing import List, Optional, Mapping, Tuple

import html2text
import requests
from bs4 import BeautifulSoup, Tag
from requests import Response

from fuzzywuzzy import fuzz, process

log = logging.getLogger(__name__)

RHLP_URL="http://rhlp-oskutka.8a09.starter-us-east-2.openshiftapps.com"

class LunchEntity:
    def __init__(self, name: str, url=None, display_name=None, tags=None, selector=None, request_params=None):
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
        return self._display_name

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
            result += f" ({display_name})"
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
    
    @property
    def instances(self) -> Mapping[str, LunchEntity]:
        return self._instances


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

    def register_instances(self):
        # TODO - Load from file
        globus_selector = ".restaurant__menu-table-row--active"
        self.register('nepal', url='Nepal', selector=None, cls=RHLPLunch)
        self.register('globus', url='Globus', selector=globus_selector, cls=RHLPLunch)
        self.register('kocka', url='ZelenaKocka', selector="#dnesni-menu", cls=RHLPLunch)
        self.register('purkynka', url='Purkynka', cls=RHLPLunch)
        self.register('a-sport', url='Sporthotel', cls=RHLPLunch)
        self.register('pad-thai', url='PadThai', cls=RHLPLunch)
        self.register('buddha', url='http://www.indian-restaurant-buddha.cz/index.html', selector="#jidelnilisteklong", cls=LunchEntity)
        self.register('kytnerka', url='https://nakytnerce.cz/jidlo/#poledni', selector="#features-1", cls=LunchEntity)
        self.register('krava', url='https://www.monte-bu.cz/menu.php#poledni-section', selector="li.today", cls=LunchEntity)
        self.register('sabaidy', url='http://www.amphone.eu/restaurace', selector="li:first-child", cls=LunchEntity)
        self.register('capone', url='http://www.pizzaalcapone.cz/brno/poledni-menu', selector="p.active-day", cls=LunchEntity)
        self.register('beranek', url='https://www.ubilehoberanka.cz/menu-dne', selector="div.menu-card", cls=LunchEntity)
        self.register('seminar', url='http://www.useminaru.cz/menu.php', selector=".maintab .bold", cls=LunchEntity)

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


def to_text(content):
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.ignore_tables = True
    h.ignore_emphasis = True
    return h.handle(str(content)).strip()
