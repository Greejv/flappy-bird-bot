#!/bin/bash
# Builds dist/FlappyBot-mac.zip - the file people download from Releases.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:-dev}"
OUT=dist/FlappyBot
rm -rf dist && mkdir -p "$OUT"
cp -R flappybot requirements.txt "Start Bot.command" "$OUT/"
cp docs/HOW-TO-START.txt "$OUT/HOW TO START.txt"
python3 scripts/tutorial_html.py "$OUT/tutorial"   # illustrated guide (needs: pip install markdown)
echo "$VERSION" > "$OUT/flappybot/VERSION"
find "$OUT" -name '__pycache__' -prune -exec rm -rf {} +
chmod +x "$OUT/Start Bot.command"
(cd dist && zip -qrX "FlappyBot-mac.zip" FlappyBot)
echo "built dist/FlappyBot-mac.zip ($VERSION)"
