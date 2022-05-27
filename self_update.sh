#! /bin/bash 

PROJECT_ROOT="${1}"

echo "Project ROOT: ${PROJECT_ROOT}"

cd "${PROJECT_ROOT}"
git pull --force origin master

if [ -e "$HOME/.poetry/bin" ]; then
  export PATH="$HOME/.poetry/bin:$PATH"
fi

poetry install

poetry run python -m pyluch import -O "${PROJECT_ROOT}/resources/restaurants.yml"