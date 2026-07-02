# Implementation Log

## 2026-04-08

### Discovery

- Cloned `TRNOG/hosting-outbound-logger` into `repo/hosting-outbound-logger`.
- Verified that the upstream repository is intentionally minimal and currently contains only:
  - `README.md`
  - `install.sh`
  - `LICENSE`
- Confirmed that the real collector implementation is generated dynamically by `install.sh` into `/opt/outbound-logger/logger.py`.
- Confirmed that the upstream runtime model is:
  - Python + BCC collector
  - systemd-managed service
  - stdout to journald
  - rsyslog fan-out to local file and/or remote syslog
- Identified a concrete compatibility issue in upstream `csv` mode: rsyslog matching is JSON-specific, so CSV output will not be routed reliably without changes.

### Initial Architecture Decision

- Backend stack: Python
  Chosen because the upstream collector is already Python/BCC and can be preserved with minimal translation.
- HTTP/service layer: FastAPI with server-rendered templates and static assets
  Chosen for a small dependency footprint, easy API construction, and straightforward SSE support.
- Realtime delivery: Server-Sent Events
  Chosen because the dashboard is primarily one-way live monitoring and SSE is simpler to operate than WebSockets for this use case.
- State model: in-memory ring buffer plus derived summaries
  Chosen for a functional first version with low complexity. File export compatibility will remain separate from the live API state.
- Panel integration direction: WHM-first
  Chosen because outbound connection monitoring is an administrative/security function rather than an end-user cPanel feature.

### Planned Project Structure

- `core/`
  Source-controlled adaptation of the upstream collector logic and event schema.
- `service/`
  FastAPI app, config loading, event store, SSE stream, and API routes.
- `web/`
  Templates, CSS, and browser-side JavaScript.
- `cpanel/`
  WHM plugin scaffold, embedding/proxy helpers, and install assets.
- `scripts/`
  Install, uninstall, dev-run, and packaging helpers.
- `deploy/systemd/`
  systemd unit file for the combined service.
- `config/`
  Example YAML configuration.
- `docs/`
  Analysis, implementation log, architecture notes, and install guidance.

### Assumptions

- The service will default-bind to `127.0.0.1` and a configurable port.
- A reverse proxy or panel-side proxy/iframe path will be used when browser access is needed beyond localhost.
- The first implementation will keep the upstream logger behavior as intact as practical while reorganizing it into source-controlled modules.
- Because this development environment is Windows, BCC/eBPF execution and systemd validation cannot be run locally here. Linux runtime verification will remain a documented next step.

### Immediate Next Steps

1. Extract and refactor the upstream generated Python logger into `core/`.
2. Implement config loading and a backend service scaffold.
3. Add API endpoints and an SSE event stream.
4. Build the initial dashboard UI.
5. Add WHM integration scaffold and operational scripts.

### Implemented Since Initial Plan

- Added `core/models.py` with a source-controlled internal event model and JSON/CSV serialization helpers.
- Added `core/collector.py` by adapting the upstream generated Python logger into an importable module with a callback-based runtime.
- Added `service/config.py` for YAML configuration loading with sensible defaults.
- Added `service/runtime.py`, `service/store.py`, `service/realtime.py`, and `service/sinks.py`.
- Added `service/app.py` with:
  - `/health`
  - `/api/summary`
  - `/api/events`
  - `/api/top/destinations`
  - `/api/top/users`
  - `/api/top/ports`
  - `/events/stream`
- Added a responsive dashboard in:
  - `web/templates/dashboard.html`
  - `web/static/app.css`
  - `web/static/app.js`
- Added a WHM integration scaffold:
  - `cpanel/whm/appconfig/trnog-outbound-monitor.conf`
  - `cpanel/whm/cgi/trnog_outbound_monitor.cgi`
  - `cpanel/whm/assets/trnog-outbound-monitor.png`
- Added deployment and ops files:
  - `config/config.example.yaml`
  - `scripts/install.sh`
  - `scripts/uninstall.sh`
  - `scripts/dev-run.sh`
  - `deploy/systemd/trnog-outbound-monitor.service`
- Added operator-facing docs:
  - `README.md`
  - `docs/architecture.md`

### Validation Performed

- Ran `python -m compileall core service`.
- Ran `python -m py_compile cpanel/whm/cgi/trnog_outbound_monitor.cgi`.
- Refreshed top-level `README.md` for GitHub publishing with explicit beta/runtime validation status.

### Unresolved Issues

- The embedded collector cannot be executed in this Windows workspace because BCC/eBPF and systemd are Linux-only runtime dependencies.
- WHM plugin registration and proxy behavior still need end-to-end validation on a real cPanel/WHM server.
- The `tail` compatibility mode currently follows a single file path and does not yet auto-track rotated daily files.

### Next Practical Linux Validation Steps

1. Run `./scripts/install.sh` on an AlmaLinux or Rocky Linux cPanel host.
2. Confirm `/health` reports `running` in `embedded` mode.
3. Generate outbound traffic with `curl https://example.com`.
4. Verify API responses, dashboard refresh, exported log output, and WHM access path.
