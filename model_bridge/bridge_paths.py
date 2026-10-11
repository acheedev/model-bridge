"""Resolved filesystem boundaries shared by the bridge and its CLI runner."""
import os
from pathlib import Path

APPROVED_ROOTS = (Path('/home/jachee/projects'), Path('/home/jachee/.codex'))
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def approved_path(path):
    resolved = Path(path).expanduser().resolve()
    if not any(resolved.is_relative_to(root) for root in APPROVED_ROOTS):
        raise ValueError('Bridge paths must resolve under /home/jachee/projects or /home/jachee/.codex.')
    return resolved


def transcript_directory():
    return approved_path(os.environ.get('BRIDGE_DATA_DIR', PROJECT_ROOT / 'transcripts'))
