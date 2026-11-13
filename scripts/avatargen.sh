#!/usr/bin/env bash
# Startet die Desktop-Anwendung (Fenster statt Browser). Wird auch vom Menü-Eintrag benutzt.
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
# shellcheck disable=SC1091
source .venv/bin/activate
exec python -m app.desktop "$@"
