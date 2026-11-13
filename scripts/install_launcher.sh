#!/usr/bin/env bash
# Richtet die Desktop-Anwendung ein: pywebview in der venv und Eintrag im Anwendungsmenü.
# Vorher (einmalig, mit sudo):
#   sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 \
#        gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
source .venv/bin/activate
# Die venv braucht Zugriff auf die System-Pakete (PyGObject/GTK); eigene Pakete der venv haben Vorrang.
sed -i 's/^include-system-site-packages = false/include-system-site-packages = true/' .venv/pyvenv.cfg
python -m pip install pywebview
python -c "import gi; gi.require_version('Gtk','3.0'); import webview; print('pywebview + GTK: ok')" \
  || echo "HINWEIS: GTK/WebKit nicht nutzbar - die App fällt auf Chromium/Chrome im App-Modus zurück."
python -m app.launcher install
