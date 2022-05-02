import datetime
import json
from pathlib import Path


class VisitorInfo:
    def __init__(self, id: str, ua: str, ip: str, query: str = ""):
        self.v = 1
        self.id: str = id
        self.ua: str = ua
        self.ip: str = ip
        self.query: str = query

    def dump_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


class VisitorService:
    def __init__(self, base: Path) -> None:
        self.root: Path = base / 'visitors'

    def store(self, id: str, info: 'VisitorInfo') -> None:
        pth = self._pth(id)

        if not pth.exists():
            pth.mkdir(parents=True)

        fname = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fp = pth / f"{fname}.json"
        fp.write_text(info.dump_json())

    def _pth(self, id: 'id') -> Path:
        return self.root / id
