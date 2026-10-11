"""Print supported model/effort combinations from the installed CLI, offline."""
import json

from .codex_runner import CodexFailure, consultation_deadline, discover_capabilities


if __name__ == '__main__':
    try:
        print(json.dumps({'source': 'installed_cli_bundled_catalog',
                          'models': discover_capabilities(deadline=consultation_deadline(30))}, indent=2))
    except CodexFailure as exc:
        print(json.dumps({'status': 'error', 'error': exc.error}))
        raise SystemExit(1)
