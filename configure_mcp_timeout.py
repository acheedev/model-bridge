"""Align this bridge's Codex MCP client timeout without printing configuration."""
import argparse
import os
import re
import stat
import tempfile
from pathlib import Path

from codex_runner import mcp_timeout_seconds


def aligned_config(text, seconds):
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines)
                  if re.fullmatch(r'\s*\[mcp_servers\.model-bridge\]\s*(?:#.*)?', line.strip())), None)
    if start is None:
        raise ValueError('Missing [mcp_servers.model-bridge] section.')
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith('[')), len(lines))
    matches = [i for i in range(start + 1, end) if re.match(r'\s*tool_timeout_sec\s*=', lines[i])]
    if len(matches) > 1:
        raise ValueError('Duplicate model-bridge tool timeout settings.')
    setting = f'tool_timeout_sec = {seconds}\n'
    if matches:
        lines[matches[0]] = setting
    else:
        if not lines[start].endswith('\n'):
            lines[start] += '\n'
        lines.insert(start + 1, setting)
    return ''.join(lines)


def configure(path):
    seconds = mcp_timeout_seconds()
    text = path.read_text(encoding='utf-8')
    updated = aligned_config(text, seconds)
    if updated != text:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), stat.S_IMODE(path.stat().st_mode))
                stream.write(updated)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return seconds


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml')
    args = parser.parse_args()
    try:
        print(f'model-bridge tool_timeout_sec = {configure(args.config)}')
    except (OSError, ValueError) as exc:
        # Never include paths, exception text, or configuration contents.
        parser.exit(1, f'MCP timeout update failed ({type(exc).__name__}).\n')
