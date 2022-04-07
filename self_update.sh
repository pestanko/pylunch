#! /bin/bash 

PROJECT_ROOT = "${1}"

echo "Project ROOT: ${PROJECT_ROOT}"

cd ${PROJECT_ROOT}
git pull --force origin master

poetry install

poetry run python -m pyluch import -O "${PROJECT_ROOT}/resources/restaurants.yml"