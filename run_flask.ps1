$env:FLASK_APP="pylunch/web.py"
$env:FLASK_ENV="development"


pipenv run python -m flask run -h 0.0.0.0 -p 8000 