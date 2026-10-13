"""Bounded text bundles and cooperative, separately authorized application."""
import base64
import difflib
import hashlib
import json
import os
import stat
from pathlib import Path
from .file_transfers import directory, read_file, write_file, valid_name, FILE_BYTES, TOTAL_BYTES

REPO_PARENT = Path('/home/jachee/projects/acheedev')
EXCLUDED = {'.git', '.codex', '.agents', '.venv', 'venv', '__pycache__', '.pytest_cache',
            '.tmp', '.worker-inputs', 'job-data', 'transcripts', 'private', 'node_modules', 'data'}
STAGE_BYTES = 1024**3

class StageError(ValueError):
    def __init__(self, code, *, path=None, file_type=None):
        super().__init__(code)
        self.details = {key: value for key, value in
                        (('path', str(path) if path is not None else None), ('file_type', file_type))
                        if value is not None}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def target_path(value):
    if not isinstance(value, str) or not value or len(value.encode()) > 512:
        raise StageError('invalid_target_path')
    parts = value.split('/')
    if value.startswith('/') or any(part in ('', '.', '..') or part.casefold() in EXCLUDED for part in parts):
        raise StageError('excluded_or_invalid_target')
    for part in parts:
        valid_name(part)
    return Path(*parts)

def repo_root(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_relative_to(REPO_PARENT) or path == REPO_PARENT:
        raise StageError('unauthorized_repo_root')
    with directory(path):
        pass
    return path

def entry(root, relative):
    path = target_path(relative)
    # Missing ancestor means expected absence, but symlinks/special files fail closed.
    try:
        with directory(Path(root) / path.parent) as fd:
            try:
                info = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                return {'exists': False}, None
            data = read_file(fd, path.name, FILE_BYTES)
            return {'exists': True, 'sha256': digest(data), 'mode': stat.S_IMODE(info.st_mode)}, data
    except FileNotFoundError:
        return {'exists': False}, None

def baseline(root, paths):
    if not isinstance(paths, list) or not 1 <= len(paths) <= 8 or len(set(paths)) != len(paths):
        raise StageError('target_paths_required_max_8')
    result = {}
    total = 0
    for path in paths:
        info, data = entry(root, path)
        if data is not None:
            data.decode('utf-8')
            total += len(data)
        result[path] = info
    if total > TOTAL_BYTES:
        raise StageError('target_base_limit_exceeded')
    return result

def snapshot(root, destination, check_content):
    destination.mkdir(mode=0o700)
    total = 0
    def copy(source, dest):
        nonlocal total
        with directory(source) as fd:
            for name in sorted(os.listdir(fd)):
                if name.casefold() in EXCLUDED:
                    continue
                try:
                    valid_name(name)
                except ValueError:
                    continue
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    continue
                if stat.S_ISDIR(info.st_mode):
                    child = dest / name
                    child.mkdir(mode=0o700)
                    copy(source / name, child)
                elif stat.S_ISREG(info.st_mode):
                    data = read_file(fd, name, STAGE_BYTES)
                    check_content(data)
                    total += len(data)
                    if total > STAGE_BYTES:
                        raise StageError('stage_limit_exceeded')
                    with directory(dest) as out:
                        write_file(out, name, data)
                        os.chmod(name, stat.S_IMODE(info.st_mode) & 0o777, dir_fd=out, follow_symlinks=False)
                else:
                    raise StageError('special_file_excluded')
    copy(Path(root), destination)
    return total

def bundle(job, stage, base_data):
    operations, artifacts, patch = [], [], []
    total = 0
    # Refuse undeclared changes; temporary worker scratch is explicitly excluded.
    current = inventory(stage)
    original = job['snapshot_inventory']
    changed = {path for path in current.keys() | original.keys() if current.get(path) != original.get(path)}
    if changed - set(job['target_paths']):
        raise StageError('undeclared_stage_changes')
    for index, relative in enumerate(job['target_paths']):
        before = job['base_manifest'][relative]
        after, data = entry(stage, relative)
        if before == after:
            continue
        old = base_data[relative] or b''
        new = data or b''
        old_text, new_text = old.decode('utf-8'), new.decode('utf-8')
        artifact = None
        if data is not None:
            artifact = f'after-{index}.txt'
            artifacts.append((artifact, data))
            total += len(data)
        if total > TOTAL_BYTES:
            raise StageError('bundle_limit_exceeded')
        operations.append({'path': relative, 'before': before, 'after': after, 'artifact': artifact})
        for line in difflib.unified_diff(old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
                     fromfile='a/' + relative if before['exists'] else '/dev/null',
                     tofile='b/' + relative if after['exists'] else '/dev/null'):
            patch.append(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n')
    result = {'version': 1, 'job_id': job['job_id'], 'project_id': job['project_id'],
              'base_hash': digest(encoded(job['base_manifest'])), 'operations': operations}
    raw = encoded(result)
    diff = ''.join(patch).encode()
    if len(raw) > FILE_BYTES or len(diff) > FILE_BYTES:
        raise StageError('patch_limit_exceeded')
    return result, [('bundle.json', raw), ('changes.diff', diff)] + artifacts

def inventory(root):
    result = {}
    def walk(path, prefix=''):
        with directory(path) as fd:
            for name in os.listdir(fd):
                if name == '.tmp':
                    continue
                valid_name(name)
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                relative = prefix + name
                if stat.S_ISDIR(info.st_mode):
                    walk(path / name, relative + '/')
                else:
                    data = read_file(fd, name, STAGE_BYTES)
                    result[relative] = (digest(data), stat.S_IMODE(info.st_mode))
    walk(Path(root))
    return result

def managed_size(root, runtime_roots=()):
    """Count regular bytes; tolerate transient entries only inside exact worker homes.

    Never follow links. Regular runtime files still count toward admission.
    All storage outside the supplied homes remains strict.
    """
    root = Path(root)
    runtime_roots = tuple(Path(path) for path in runtime_roots)
    runtime = any(root == path or root.is_relative_to(path) for path in runtime_roots)
    total = 0
    try:
        with directory(root) as fd:
            for name in os.listdir(fd):
                path = root / name
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    if runtime or path in runtime_roots:
                        continue
                    raise
                if stat.S_ISDIR(info.st_mode):
                    total += managed_size(path, runtime_roots)
                elif stat.S_ISREG(info.st_mode):
                    total += info.st_size
                elif not runtime:
                    raise StageError('unsafe_managed_storage', path=path,
                                     file_type=stat.filemode(info.st_mode)[0])
    except FileNotFoundError:
        if not runtime:
            raise
    return total
