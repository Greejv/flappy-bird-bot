#!/bin/bash
# Double-click me to start the Flappy money bot.
cd "$(dirname "$0")" || exit 1
VENV="$HOME/.flappybot-venv"

pick_python() {
  for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
           /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/bin/python3; do
    if [ -x "$p" ] && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      echo "$p"; return 0
    fi
  done
  return 1
}

if ! PY=$(pick_python); then
  echo "Python 3 is needed (one time). macOS will now offer to install the"
  echo "'Command Line Developer Tools' - click Install, wait, then double-click"
  echo "'Start Bot.command' again. (Or install Python from https://www.python.org)"
  xcode-select --install 2>/dev/null
  read -r -p "Press ENTER to close..."
  exit 1
fi

STAMP="$VENV/.requirements-$(shasum requirements.txt | cut -c1-12)"
if [ ! -f "$STAMP" ]; then
  echo "First start: setting things up (about a minute, needs internet)..."
  rm -rf "$VENV"
  "$PY" -m venv "$VENV" || { echo "Could not create Python environment"; read -r -p "Press ENTER..."; exit 1; }
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  if ! "$VENV/bin/python" -m pip install --quiet -r requirements.txt; then
    echo "Installing dependencies failed. Check your internet connection and try again."
    read -r -p "Press ENTER to close..."
    exit 1
  fi
  touch "$STAMP"
fi

"$VENV/bin/python" -m flappybot "$@"
echo
read -r -p "Bot stopped. Press ENTER to close this window..."
