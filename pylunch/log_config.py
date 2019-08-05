import logging.config
import os

LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG')
LOG_LEVEL_DPMB = os.getenv('LOG_LEVEL_PYLUNCH', LOG_LEVEL)

LOGGING = {
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
    },
    'loggers': {
        'pylunch': {'handlers': ['console'], 'level': LOG_LEVEL_DPMB},
    }
}


def load():
    logging.config.dictConfig(LOGGING)
