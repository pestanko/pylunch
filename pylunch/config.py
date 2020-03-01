import collections
from typing import MutableMapping, Union, Any
from pathlib import Path
import tempfile
import logging
import yaml
import os
import functools

from pylunch import utils

log = logging.getLogger(__name__)
CACHE_DIR = Path(tempfile.gettempdir()) / 'pylunch'


def load_yaml(file: Union[Path, str]) -> MutableMapping[str, Any]:
    file = Path(file)

    if not file.exists():
        log.warning(f"[LOAD] Config file not exists: {file}")
        return {}
    with file.open("r") as fp:
        return yaml.safe_load(fp)


def save_yaml(file: Union[Path, str], content: MutableMapping):
    file = Path(file)

    if not file.parent.exists():
        log.warning(f"[SAFE] Unnable to safe config file (directory not exists): {file}")
        return
    with file.open("w") as fp:
        yaml.safe_dump(content, fp)


class YamlLoader:
    def __init__(self, base_dir: Union[str, Path], file: Union[str, Path]):
        self.base_dir = Path(base_dir)
        self.file = Path(file)

    @property
    def full_path(self) -> Path:
        return self.real_path(self.file)

    def load(self) -> MutableMapping:
        file = self.real_path(self.file)
        content = load_yaml(file)
        return content

    def save(self, data: MutableMapping):
        file = self.real_path(self.file)
        log.info(f"[SAVE] Saving content ({file}): {data}")
        save_yaml(file, data)

    def real_path(self, path: Union[str, Path] = None) -> Path:
        path = path if path is not None else self.file
        if path.is_absolute():
            return path
        return self.base_dir / path


class AppConfig(collections.MutableMapping):
    def __init__(self, **kwargs):
        self._config = {**kwargs}

    @property
    def config(self) -> MutableMapping[str, Any]:
        return self._config

    def __getitem__(self, k):
        return self.config.get(k)

    def __setitem__(self, k, v):
        self.config[k] = v

    def __delitem__(self, k):
        del self.config[k]

    def __iter__(self):
        return iter(self.config)

    def __len__(self):
        return len(self.config)

    @property
    def restaurants(self) -> Path:
        return Path(self.config.get('restaurants', './restaurants.yml'))

    @property
    def use_cache(self) -> bool:
        return not self.config.get('no_cache', False)

    @property
    def cache_dir(self) -> Path:
        return Path(self.config.get('cache_dir', os.getenv('PYLUNCH_CACHE_DIR', CACHE_DIR)))

    @property
    def format(self) -> str:
        return self.config.get('format', 'text')

    @property
    def zomato_key(self) -> str:
        return self.config.get('zomato_key', None)

    @property
    def telegram_token(self) -> str:
        return self.config.get('telegram_token', None)

    @property
    def discord_token(self) -> str:
        return self.config.get('discord_token', None)

    @property
    def default_source(self) -> str:
        return self.get('default_source')

