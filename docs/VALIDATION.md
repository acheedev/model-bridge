# Repository layout validation

Validated October 11, 2026, using the existing Ubuntu WSL Python 3.10.12 virtual
environment against a disposable copy of this checkout under
`/home/jachee/projects/`. The copy was removed after validation. The installed
service and its checkout/data were not modified.

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 93 tests passed; unittest reported 2.360 seconds. |
| `python -m compileall -q model_bridge tests` | Passed on Linux and Windows. |
| `bash -n scripts/mbridge.sh` | Passed. |
| `git diff --check` | Passed. |
| Local Markdown navigation | Relative file links resolve. |
| Private inventory exclusion | `private/` is ignored and has no tracked files. |

Two regression checks cover the package move: transcript/temp paths still resolve
to the checkout root, and the job allowlist and private worker launcher still use
that same root. Existing tests cover relative imports through actual server/tool
registration, job subprocess execution, resource limits, and cancellation.

This was local validation without live model requests. Authentication to provider
backends, installed service startup, client discovery, reboot availability, and
model-driven project completion remain unverified here. Earlier CLI/Code Mode
diagnostics in [operations](OPERATIONS.md) remain historical observations.

The user reported that the bridge service is stopped. Its installed unit must
adopt the new module entry point before a separately authorized restart; the
repository template is [deploy/model-bridge.service](../deploy/model-bridge.service).
No commit, push, installation, or service restart was performed.

The test runner measured suite duration. Task start, implementation completion,
and validation completion timestamps were not captured; total task duration is
unknown.
