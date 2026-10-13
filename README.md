# Model Bridge

An authenticated, loopback-only MCP service for independent Claude/Codex/Gemini
consultations, readable transcripts, byte-preserving file transfers, and
explicitly authorized project jobs.

**Start here:** [Project checklist](docs/TASKS.md). Check off work as its stated
completion evidence becomes available.

Current staged pilot: [local delivery and remaining activation proof](docs/STAGED_PILOT_2026-10-12.md). Source changes are not yet installed-service proof.

## Project layout

```text
model_bridge/  Python package: server, runners, transfers, and job management
tests/         Automated tests and the explicit worker sandbox probe
docs/          Specification, operations guide, tool schemas, and task checklist
scripts/       Local launch scripts
deploy/        Service configuration maintained in the repository
```

Runtime data stays at the checkout root in Git-ignored `transcripts/`,
`job-data/` and `.tmp/`; legacy `.worker-inputs/` remains ignored. New inputs/stages are per job under `job-data/`. Private inventory belongs in
Git-ignored `private/`; actual credentials stay in their protected files.

## Documentation

- [Task checklist](docs/TASKS.md): current progress and ordered next steps.
- [Project specification](docs/PROJECT_SPEC.md): direction, roles, authority, and release scope.
- [Operations guide](docs/OPERATIONS.md): setup, consultation contracts, security, and validation.
- [Project work guide](docs/MCP_PROJECT_WORK.md): transfers, jobs, recovery, and client proof.
- [Tool schemas](docs/MCP_TOOL_SCHEMAS.json): exact worker-transfer input contracts.

## Run and check

The runtime targets Ubuntu WSL/Linux and Python 3.10+. From the checkout root,
with the existing virtual environment and dependencies configured:

```bash
bash scripts/mbridge.sh
```

The script retains the existing CLI/model settings. See the operations guide
before changing authentication, executable paths, or service configuration.
The maintained systemd unit is now `deploy/model-bridge.service` and starts
`python -m model_bridge.claude_bridge`. An already installed unit needs a
separately authorized update and service restart to adopt the new entry point.

Run local checks without a live consultation:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q model_bridge tests
git diff --check
```

Run the package from the checkout root. Optional editable installation is
available through `.venv/bin/python -m pip install -e .`. Launching individual
package files by filename is replaced by module commands, for example
`.venv/bin/python -m model_bridge.codex_capabilities`.
