import logging.config
import os

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
