#! /bin/bash

export FLASK_APP="pylunch/web.py"
export FLASK_ENV=development

pipenv run flask run -h 0.0.0.0 -p 8000


