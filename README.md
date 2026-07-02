# TRNOG Outbound Monitor

> Open-source outbound connection monitoring service and WHM integration layer built around the original **TRNOG/hosting-outbound-logger** project.

[![Status](https://img.shields.io/badge/status-beta-orange.svg)]()
[![Platform](https://img.shields.io/badge/platform-Linux-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)]()
[![License](https://img.shields.io/badge/license-Open%20Source-lightgrey.svg)]()

---

## Overview

TRNOG Outbound Monitor extends the original **TRNOG/hosting-outbound-logger** by preserving its eBPF/BCC outbound monitoring logic while providing a complete service layer suitable for long-term deployment and integration.

The project wraps the original collector with:

- Long-running backend service
- REST JSON API
- Realtime web dashboard
- WHM integration scaffold
- Installation and removal tooling
- Modular project structure

---

# Table of Contents

- [Project Status](#project-status)
- [Why This Exists](#why-this-exists)
- [Architecture](#architecture)
- [Feature Set](#feature-set)
- [API](#api)
- [Project Layout](#project-layout)
- [Configuration](#configuration)
- [Installation](#installation)
- [Development](#development)
- [Uninstall](#uninstall)
- [WHM Integration](#whm-integration)
- [Upstream Preservation](#upstream-preservation)
- [Known Gaps](#known-gaps)
- [Release Recommendation](#release-recommendation)
- [License](#license)

---

# Project Status

Current status:

> **Beta / First Functional Scaffold**

### What's implemented

- Structured and installable project
- Embedded outbound collector
- FastAPI backend
- REST API
- Live dashboard
- Server-Sent Events
- WHM integration scaffold
- Install & uninstall tooling
- Python syntax validation
- Source-controlled collector modules

### Not yet production validated

This project has **not yet** been fully runtime-tested on:

- cPanel/WHM production systems
- AlmaLinux
- Rocky Linux
- Ubuntu
- Debian
- Multiple kernel versions with BCC/eBPF

Publish this repository as:

- Beta
- Work in Progress
- Needs Linux/cPanel validation

**Do not publish as:**

- Stable
- Production Ready

---

# Will It Break cPanel?

Short answer:

> It is designed not to modify or interfere with cPanel itself, but production safety cannot honestly be guaranteed until runtime validation has been completed.

The project:

- does **not** patch cPanel files
- installs an independent systemd service
- exposes the backend only on localhost
- communicates with WHM through a lightweight CGI proxy

Remaining validation areas include:

- BCC package availability
- Kernel header compatibility
- eBPF attachment permissions
- WHM AppConfig registration
- Localhost proxy behavior
- WHM ACL compatibility

Recommended validation process:

1. Install on a staging server
2. Verify service startup
3. Check `/health`
4. Confirm outbound events
5. Verify WHM UI
6. Test complete uninstall

---

# Why This Exists

The original **hosting-outbound-logger** is distributed as a dynamically generated installer.

While useful, this makes:

- maintenance
- testing
- packaging
- version control
- panel integration

more difficult.

This project reorganizes the collector into a proper open-source repository.

---

# Architecture

```
eBPF / BCC
      │
      ▼
 Embedded Collector
      │
      ▼
 Backend Service
      │
 ┌────┴─────────┐
 │              │
 ▼              ▼
REST API     SSE Stream
 │              │
 └──────┬───────┘
        ▼
 Web Dashboard
        │
        ▼
 WHM Proxy
```

---

# Upstream Preservation

The original repository was cloned and audited before implementation.

Reference paths:

```
repo/
└── hosting-outbound-logger/

docs/
└── repo-analysis.md
```

The following core logic was preserved:

- eBPF outbound connect probes
- Event model
- PID resolution
- UID resolution
- Process metadata
- Optional DNS enrichment
- Optional SNI enrichment
- Loopback filtering
- Private network filtering
- Root process filtering

---

# Feature Set

## Implemented

- Embedded Python collector
- FastAPI backend
- Health endpoint
- REST API
- Server-Sent Events
- Responsive dashboard
- Live event table
- Filtering support
- Daily export (optional)
- Syslog forwarding (optional)
- WHM integration scaffold
- Install & uninstall scripts

### Filters

- Time range
- User
- Destination IP
- Port
- IP family
- Free-text search

---

## Collector Modes

### Embedded

Runs the bundled collector directly.

### Tail

Reads an existing upstream log file.

---

# API

Available endpoints:

| Endpoint | Description |
|----------|-------------|
| `/health` | Service health |
| `/api/summary` | Dashboard summary |
| `/api/events` | Event list |
| `/api/top/destinations` | Top destination IPs |
| `/api/top/users` | Top users |
| `/api/top/ports` | Top ports |
| `/events/stream` | Live Server-Sent Events |

---

# Project Layout

```
core/
    Collector implementation

service/
    Backend service
    Runtime
    API
    Storage
    Event broadcasting

web/
    Dashboard
    Templates
    Static assets

cpanel/
    WHM integration
    CGI proxy
    AppConfig

scripts/
    Install
    Uninstall
    Development

deploy/systemd/
    systemd service

config/
    Example configuration

docs/
    Documentation

repo/
    Upstream reference
```

---

# Configuration

Example configuration:

```
config/config.example.yaml
```

Main options:

```yaml
http:
  host:
  port:
  localhost_only:

collector:
  mode:
  log_source_path:
  ignore_loopback:
  ignore_private:
  ignore_root:
  enable_host_enrichment:

export:
  mode:
  format:
```

Default service bind:

```
127.0.0.1:15155
```

---

# Installation

```bash
chmod +x scripts/install.sh scripts/uninstall.sh scripts/dev-run.sh

./scripts/install.sh
```

The installer currently:

- Installs Python dependencies
- Installs BCC where possible
- Copies files to

```
/opt/trnog-outbound-monitor
```

Creates:

```
/etc/trnog-outbound-monitor/config.yaml
```

Then:

- Creates virtual environment
- Installs Python requirements
- Installs systemd service
- Starts service
- Installs WHM integration (if available)

---

# Development

```bash
python3 -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

./scripts/dev-run.sh
```

If BCC is unavailable the backend still starts, but collector health will be degraded unless **tail mode** is used.

---

# Uninstall

```bash
./scripts/uninstall.sh
```

Complete removal:

```bash
./scripts/uninstall.sh --purge
```

`--purge` additionally removes:

- Configuration
- Logs
- Runtime state

---

# WHM Integration

Installed assets:

### CGI Proxy

```
/usr/local/cpanel/whostmgr/docroot/cgi/trnog_outbound_monitor.cgi
```

### Icon

```
/usr/local/cpanel/whostmgr/docroot/addon_plugins/trnog-outbound-monitor.png
```

### AppConfig

```
/opt/trnog-outbound-monitor/cpanel/whm/appconfig/trnog-outbound-monitor.conf
```

The WHM integration is intentionally **administrator-first**, as outbound telemetry is server-wide infrastructure.

---

# Documentation

```
docs/
├── architecture.md
├── implementation-log.md
└── repo-analysis.md
```

---

# Known Gaps

Current limitations:

- Runtime validation on real Linux servers
- End-to-end WHM validation
- Automatic log rotation support in Tail mode
- Persistent historical database

---

# Release Recommendation

Suggested release:

```
v0.1.0-beta
```

Suggested subtitle:

> First working TRNOG outbound monitor service scaffold with WHM integration.

---

# License

This repository preserves compatibility with the original upstream project intent and is suitable for open-source release under **TRNOG**.
