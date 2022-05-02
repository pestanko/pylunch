import datetime
import json
from pathlib import Path

from pylunch import log_config


class VisitorInfo:
    def __init__(self, id: str, ua: str, ip: str, query: str = ""):
        self.v = 1
        self.id: str = id
        self.ua: str = ua
        self.ip: str = ip
        self.query: str = query or ''

    def dump_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)

    def dump(self) -> str:
        return f"id: {self.id}; ip: {self.ip}; q: {self.query}; ua: {self.ua}"


class VisitorService:
    def __init__(self, base: Path) -> None:
        self.root: Path = base / 'visitors'

    def store(self, vid: str, info: 'VisitorInfo') -> None:

        if not self.root.exists():
            self.root.mkdir(parents=True)

        now = datetime.datetime.now()
        day = now.strftime("%Y_%m_%d")
        log = log_config.for_visitor(self.root, day)
        log.info(info.dump())
