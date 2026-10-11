#!/bin/bash

CLAUDE_MODEL=claude-haiku-5-5 \
BRIDGE_MAX_TOKENS=4096 \
CODEX_TIMEOUT_SECONDS=120 \
CODEX_BIN='/home/jachee/.vscode-server/extensions/openai.chatgpt-26.1007.21434-linux-x64/bin/linux-x86_64/codex' \
exec "$HOME/projects/acheedev/model-bridge/.venv/bin/python" \
"$HOME/projects/acheedev/model-bridge/claude_bridge.py"
