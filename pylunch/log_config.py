import logging.config
import os
from pathlib import Path

LOG_LEVEL = os.getenv('LOG_LEVEL', 'WARNING')
LVL_MAP = dict(w='WARNING', d='DEBUG', i='INFO', e='ERROR')


def make_cfg(level=None):
    lvl = LOG_LEVEL
    if level is not None:
        lvl = LVL_MAP.get(level.lower(), LOG_LEVEL)

    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(asctime)s - %(module)s: %(message)s'
            },
            'simple': {
                'format': '%(levelname)s %(message)s'
            },
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose'
            },
            'log-file': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose'
            }
        },
        'loggers': {
            'pylunch': {'handlers': ['console'], 'level': lvl},
        }
    }


def load(level: str = None):
    cfg = make_cfg(level)
    logging.config.dictConfig(cfg)


def for_visitor(root_path: Path, day: str) -> logging.Logger:
    return create_logger(root_path, f'day_{day}')


def create_logger(root_path: Path, name: str, prefix: str = "pylunch.") -> logging.Logger:
    logger = logging.getLogger(f"{prefix}{name}")
    formatter = logging.Formatter('%(levelname)s %(asctime)s: %(message)s')
    fd = root_path / f"{name}.log"
    handler = logging.FileHandler(str(fd))
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    return logger
