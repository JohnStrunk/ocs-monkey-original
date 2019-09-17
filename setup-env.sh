#!/usr/bin/env bash

VENV_NAME=venv

python3 -m venv "$VENV_NAME"

# shellcheck disable=SC1090
source "$VENV_NAME/bin/activate"

pip install --upgrade pip
pip install --upgrade -r requirements.txt

echo "Activate: . ./${VENV_NAME}/bin/activate"
