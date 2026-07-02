# Architecture Notes

## Why Python

The upstream project already implements the collector in Python with BCC, even though that code is generated dynamically by `install.sh`. This project preserves that decision and moves the collector into source-controlled Python modules so the runtime can be reviewed, tested, and extended like a normal open-source application.

## Runtime Shape

The application is split into two layers:

1. `core/`
   The collector and event model. This is where the adapted upstream eBPF logic lives.
2. `service/`
   The long-running HTTP process that owns in-memory state, file/syslog fan-out, health checks, API routes, and realtime streaming.

The web UI is served by the same HTTP process.

## Realtime Model

The service ingests events directly from the collector in `embedded` mode. This avoids re-parsing journald or rsyslog output and makes live API updates deterministic.

For migration and compatibility, a `tail` mode is also included. In that mode, the service reads JSONL or CSV lines from an existing upstream log file.

## Storage Model

The first version uses:

- an in-memory ring buffer for recent event history and aggregations
- optional daily file export
- optional raw syslog forwarding

This keeps the implementation small and production-practical while leaving room for later persistence backends if TRNOG wants indexed search, retention enforcement, or multi-node aggregation.

## WHM Integration

The plugin path is intentionally WHM-first.

This tool exposes server-wide outbound activity and security context, which is an administrative concern. End-user cPanel integration would create tenancy and authorization questions that do not exist in WHM-only scope.

The WHM integration uses:

- an AppConfig entry for menu integration
- a local CGI proxy that forwards requests to the backend on `127.0.0.1`
- ACL checks that only allow `root` or users with the `all` ACL

That keeps the service bound to localhost by default while still making the UI reachable inside WHM.

## Known Boundaries

- BCC/eBPF execution cannot be validated in this Windows development environment.
- The current `tail` mode follows a single configured file path. Daily rotation handling can be expanded later if needed.
- The initial UI is intentionally lightweight and avoids a separate frontend build pipeline.
