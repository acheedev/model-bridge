#!/bin/bash
set -euo pipefail

# Resolve the checkout even when launched from another working directory.
BRIDGE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$BRIDGE_ROOT"

CLAUDE_MODEL=claude-haiku-5-5 \
BRIDGE_MAX_TOKENS=4096 \
CODEX_TIMEOUT_SECONDS=120 \
CODEX_BIN='/home/jachee/.vscode-server/extensions/openai.chatgpt-26.1007.21434-linux-x64/bin/linux-x86_64/codex' \
exec "$BRIDGE_ROOT/.venv/bin/python" \
-m model_bridge.claude_bridge
