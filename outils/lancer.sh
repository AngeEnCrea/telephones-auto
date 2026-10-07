#!/bin/sh
# Lance le service (macOS / Linux) avec l'environnement Python du projet : http://127.0.0.1:4330/telephones/
cd "$(dirname "$0")/.." || exit 1
exec ./.venv/bin/python service/telephones.py
