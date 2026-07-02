from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class HttpConfig:
    host: str = "127.0.0.1"
    port: int = 15155
    localhost_only: bool = True


@dataclass(slots=True)
class CollectorConfig:
    mode: str = "embedded"
    log_source_path: str = "/var/log/outbound-logger/current.jsonl"
    log_format: str = "json"
    poll_interval_seconds: float = 1.0
    ignore_loopback: bool = True
    ignore_private: bool = False
    ignore_root: bool = False
    enable_host_enrichment: bool = True


@dataclass(slots=True)
class StorageConfig:
    max_events: int = 20000
    data_dir: str = "/var/lib/trnog-outbound-monitor"


@dataclass(slots=True)
class ExportConfig:
    mode: str = "file"
    format: str = "json"
    directory: str = "/var/log/trnog-outbound-monitor"
    syslog_target: str = ""
    syslog_port: int = 514
    syslog_protocol: str = "udp"


@dataclass(slots=True)
class UiConfig:
    default_window_seconds: int = 3600
    fallback_poll_seconds: int = 5
    events_limit: int = 200


@dataclass(slots=True)
class ServiceConfig:
    http: HttpConfig = field(default_factory=HttpConfig)
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    config_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["config_path"] = self.config_path
        return payload


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _candidate_paths(explicit_path: str | None = None) -> list[Path]:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    env_path = os.environ.get("TRNOG_OUTBOUND_MONITOR_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            Path("/etc/trnog-outbound-monitor/config.yaml"),
            ROOT_DIR / "config" / "config.yaml",
            ROOT_DIR / "config" / "config.example.yaml",
        ]
    )
    return candidates


def load_config(explicit_path: str | None = None) -> ServiceConfig:
    config = ServiceConfig()
    data = config.to_dict()
    selected_path: Path | None = None

    for path in _candidate_paths(explicit_path):
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        data = _deep_merge(data, loaded)
        selected_path = path
        break

    return ServiceConfig(
        http=HttpConfig(**data["http"]),
        collector=CollectorConfig(**data["collector"]),
        storage=StorageConfig(**data["storage"]),
        export=ExportConfig(**data["export"]),
        ui=UiConfig(**data["ui"]),
        config_path=str(selected_path) if selected_path else explicit_path,
    )
