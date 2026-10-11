"""Private process-group launcher; called by the job supervisor, never an MCP tool."""
import json
import os
import resource
import sys
from pathlib import Path


def main():
    if os.environ.get('MODEL_BRIDGE_CHILD') or os.environ.get('PROJECT_WORKER_CHILD'):
        raise RuntimeError('Nested project workers are disabled.')
    launch = json.loads(Path(sys.argv[1]).read_text())
    limits = launch['limits']
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (limits['memory_mb'] * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (limits['cpu_seconds'], limits['cpu_seconds'] + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    os.umask(0o077)
    os.chdir(launch['project'])
    os.execvpe(launch['argv'][0], launch['argv'], launch['environment'])


if __name__ == '__main__':
    main()
