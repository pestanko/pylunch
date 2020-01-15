import logging
from pathlib import Path
import yaml
from typing import List, Optional, Mapping, Union, MutableMapping, Any
import collections
import os.path


log = logging.getLogger(__name__)


def load_yaml(file: Union[Path, str]) -> MutableMapping[str, Any]:
    file = Path(file)

    if not file.exists():
        log.warning(f"[LOAD] Config file not exists: {file}")
        return {}
    with file.open("r") as fp:
        return yaml.safe_load(fp)

def save_yaml(file: Union[Path, str], content: dict):
    file = Path(file)

    if not file.parent.exists():
        log.warning(f"[SAFE] Unnable to safe config file (directory not exists): {file}")
        return
    with file.open("w") as fp:
        yaml.safe_dump(content, fp)


def write_instances(instances, transform=None, writer=None):
    writer = writer or print
    log.debug(f"Printing: {instances}")
    if instances is None or not instances:
        writer("**No instance has been found**")

    elif isinstance(instances, list):
        for instance in instances:
            if instance is not None:
                log.info(f"Sending one response from list: {instances}")
                writer(transform(instance))
    else:
        log.info(f"Sending one response: {instances}")
        writer(transform(instances))

def generate_nice_header(*strings):
    def _for_print(max_l, curr, char='='):
        return char * (max_l - curr)

    def _print_text(max_l, text):
        buffer = ''
        buffer += f"\n===  {text}"
        buffer +=_for_print(max_l, len(text), char=' ')
        buffer += "  ==="
        return buffer

    def _beg_end_line(max_l):
        return f"\n{_for_print(max_l + 10, 0)}"

    max_len = max(len(text) for text in strings)

    result = _beg_end_line(max_len)
    for text in strings:
        result += _print_text(max_len, text)
    result += _beg_end_line(max_len)
    return result + "\n\n"



class CollectionWrapper(collections.MutableMapping):
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


AnyPath = Union[str, Path]


def is_forward_path(root: AnyPath, path: AnyPath) -> bool:
    root = Path(root)
    path = Path(path)
    abs_path = os.path.abspath(root / path)
    abs_path = Path(abs_path)
    try:
        relative = abs_path.relative_to(root)
        relative_str = str(relative)
        return not relative_str.startswith("../")
    except ValueError:
        return False
