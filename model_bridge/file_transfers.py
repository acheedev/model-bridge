"""Private, immutable, byte-preserving transfers using pinned directory descriptors."""
import base64
import binascii
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path

INBOUND = Path('/home/jachee/projects/mcp-inbound')
OUTBOUND = Path('/home/jachee/projects/mcp-outbound')
FILE_BYTES = 2 * 1024 * 1024
TOTAL_BYTES = 8 * 1024 * 1024
FILE_COUNT = 16
REQUEST_BYTES = 12 * 1024 * 1024
RESPONSE_BYTES = 3 * 1024 * 1024
FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
RESERVED = {'manifest.json', 'auth.json', 'bridge.token', 'anthropic.key', 'codex-auth-cache.json',
            '.netrc', '.npmrc', '.gitconfig', 'credentials', 'credentials.json', 'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519'}


class TransferError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def valid_name(name):
    if not isinstance(name, str) or not name or len(name.encode('utf-8')) > 128:
        raise TransferError('invalid_filename')
    if name in ('.', '..') or any(c in name for c in '/\\:') or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise TransferError('invalid_filename')
    key = unicodedata.normalize('NFC', name).casefold()
    if key in RESERVED or key == '.env' or key.startswith('.env.') or key.endswith(('.key', '.pem', '.p12', '.pfx')):
        raise TransferError('credential_filename_excluded')
    return key


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise TransferError('invalid_transfer_id')
    return value


@contextmanager
def directory(path, create=False):
    """Pin every ancestor; never follow any directory symlink (including racing swaps)."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise TransferError('invalid_root')
    fd = os.open('/', FLAGS)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def read_file(fd, name, limit):
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise TransferError('invalid_file')
        with os.fdopen(handle, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise TransferError('file_too_large')
        return data
    finally:
        os.close(handle)


def write_file(fd, name, data):
    handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
    try:
        with os.fdopen(handle, 'wb', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(handle)
    finally:
        os.close(handle)


def publish_directory(fd, pending, final):
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    if rename(fd, pending.encode(), fd, final.encode(), 1):  # RENAME_NOREPLACE
        raise OSError(ctypes.get_errno(), 'Transfer publication failed')
    os.fsync(fd)


class TransferStore:
    def __init__(self, inbound=INBOUND, outbound=OUTBOUND, secrets_provider=lambda: ()):
        self.roots = {'inbound': Path(inbound), 'outbound': Path(outbound)}
        self.secrets_provider = secrets_provider
        for root in self.roots.values():
            if not root.is_relative_to(Path('/home/jachee/projects')):
                raise TransferError('invalid_root')
            with directory(root, create=True) as fd:
                os.fchmod(fd, 0o700)
                with self.lock(fd):
                    for name in os.listdir(fd):
                        if re.fullmatch(r'\.pending-[0-9a-f]{32}', name):
                            self.cleanup(fd, name)

    @contextmanager
    def lock(self, fd):
        handle = os.open('.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
        try:
            if not stat.S_ISREG(os.fstat(handle).st_mode):
                raise TransferError('invalid_root_lock')
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield
        finally:
            os.close(handle)

    def cleanup(self, fd, name):
        # Only flat staging directories are supported; unexpected trees fail closed.
        child = os.open(name, FLAGS, dir_fd=fd)
        try:
            for item in os.listdir(child):
                os.unlink(item, dir_fd=child)
        finally:
            os.close(child)
        os.rmdir(name, dir_fd=fd)

    def check_content(self, data):
        for secret in self.secrets_provider():
            if isinstance(secret, str):
                secret = secret.encode('utf-8')
            if secret and secret in data:
                raise TransferError('known_credential_content_excluded')

    def publish(self, direction, files):
        if direction not in self.roots or not 1 <= len(files) <= FILE_COUNT:
            raise TransferError('invalid_file_count')
        names, total = set(), 0
        for name, data in files:
            key = valid_name(name)
            if key in names:
                raise TransferError('duplicate_filename')
            names.add(key)
            self.check_content(name.encode('utf-8'))
            if not isinstance(data, bytes) or len(data) > FILE_BYTES:
                raise TransferError('file_too_large')
            total += len(data)
            self.check_content(data)
        if total > TOTAL_BYTES:
            raise TransferError('transfer_too_large')
        transfer_id = uuid.uuid4().hex
        pending = '.pending-' + transfer_id
        entries = [{'filename': name, 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in files]
        manifest = {'transfer_id': transfer_id, 'direction': direction, 'state': 'complete', 'encoding': 'base64', 'files': entries}
        with directory(self.roots[direction]) as fd, self.lock(fd):
            os.mkdir(pending, 0o700, dir_fd=fd)
            try:
                child = os.open(pending, FLAGS, dir_fd=fd)
                try:
                    for name, data in files:
                        write_file(child, name, data)
                        if read_file(child, name, FILE_BYTES) != data:
                            raise TransferError('verification_failed')
                    write_file(child, 'manifest.json', json.dumps(manifest, ensure_ascii=False).encode())
                    os.fsync(child)
                finally:
                    os.close(child)
                publish_directory(fd, pending, transfer_id)
            except BaseException:
                # Publication is all-or-nothing; crash leftovers are cleaned at startup.
                if pending in os.listdir(fd):
                    self.cleanup(fd, pending)
                raise
        return manifest

    def accept(self, files):
        if not isinstance(files, list) or not 1 <= len(files) <= FILE_COUNT:
            raise TransferError('invalid_file_count')
        if len(json.dumps(files, ensure_ascii=False).encode()) > REQUEST_BYTES:
            raise TransferError('encoded_request_too_large')
        decoded = []
        total = 0
        for entry in files:
            if not isinstance(entry, dict) or set(entry) != {'filename', 'content_base64'}:
                raise TransferError('invalid_file_schema')
            encoded = entry['content_base64']
            if not isinstance(encoded, str) or len(encoded) > 4 * ((FILE_BYTES + 2) // 3):
                raise TransferError('encoded_file_too_large')
            try:
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                raise TransferError('invalid_base64') from None
            if base64.b64encode(data).decode() != encoded:
                raise TransferError('noncanonical_base64')
            total += len(data)
            if total > TOTAL_BYTES:
                raise TransferError('transfer_too_large')
            decoded.append((entry['filename'], data))
        return self.publish('inbound', decoded)

    def load(self, direction, transfer_id):
        valid_id(transfer_id)
        if direction not in self.roots:
            raise TransferError('invalid_direction')
        try:
            with directory(self.roots[direction]) as fd:
                child = os.open(transfer_id, FLAGS, dir_fd=fd)
                try:
                    manifest = json.loads(read_file(child, 'manifest.json', 32768))
                    if not isinstance(manifest, dict) or set(manifest) != {'transfer_id', 'direction', 'state', 'encoding', 'files'} or manifest['encoding'] != 'base64':
                        raise TransferError('invalid_manifest')
                    if manifest.get('state') != 'complete' or manifest.get('transfer_id') != transfer_id or manifest.get('direction') != direction:
                        raise TransferError('incomplete_or_invalid_transfer')
                    entries = manifest['files']
                    if not 1 <= len(entries) <= FILE_COUNT:
                        raise TransferError('invalid_manifest')
                    result, names, total = [], set(), 0
                    for entry in entries:
                        if not isinstance(entry, dict) or set(entry) != {'filename', 'size_bytes', 'sha256'} or type(entry['size_bytes']) is not int or not 0 <= entry['size_bytes'] <= FILE_BYTES or not isinstance(entry['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
                            raise TransferError('invalid_manifest')
                        name = entry['filename']
                        key = valid_name(name)
                        if key in names:
                            raise TransferError('invalid_manifest')
                        names.add(key)
                        data = read_file(child, name, FILE_BYTES)
                        if len(data) != entry['size_bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                            raise TransferError('verification_failed')
                        total += len(data)
                        self.check_content(data)
                        result.append((name, data))
                    if total > TOTAL_BYTES or set(os.listdir(child)) != {name for name, _ in result} | {'manifest.json'}:
                        raise TransferError('invalid_manifest')
                    return manifest, result
                finally:
                    os.close(child)
        except FileNotFoundError:
            raise TransferError('missing_or_incomplete_transfer') from None
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            raise TransferError('invalid_transfer') from None

    def retrieve(self, direction, transfer_id, filename):
        valid_name(filename)
        manifest, files = self.load(direction, transfer_id)
        for entry, (name, data) in zip(manifest['files'], files):
            if name == filename:
                response = {'transfer_id': transfer_id, 'encoding': 'base64', **entry, 'content_base64': base64.b64encode(data).decode()}
                if len(json.dumps(response, ensure_ascii=False).encode()) > RESPONSE_BYTES:
                    raise TransferError('encoded_response_too_large')
                return response
        raise TransferError('missing_file')
