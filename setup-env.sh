#!/usr/bin/env bash

VENV_NAME=venv

python3 -m venv "$VENV_NAME"
source "$VENV_NAME/bin/activate"

pip install --upgrade pip
pip install -r requirements.txt

echo "Activate: . ./.venv/bin/activate"
