from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from typing import Any

from core.collector import CollectorSettings, CollectorUnavailableError, OutboundCollector
from core.models import CSV_FIELDS, OutboundEvent

from .config import ServiceConfig
from .realtime import EventBroadcaster
from .sinks import DailyFileSink, SyslogSink
from .store import EventStore


class ServiceRuntime:
    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.store = EventStore(config.storage.max_events)
        self.broadcaster = EventBroadcaster()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._status = "starting"
        self._started_at = datetime.now(timezone.utc)
        self._last_error = ""
        self._sinks = self._build_sinks()

    def start(self) -> None:
        target = self._run_embedded if self.config.collector.mode == "embedded" else self._run_tail
        self._thread = Thread(target=target, name="trnog-collector", daemon=True)
        self._thread.start()
        self._status = "running"

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._status = "stopped"

    def health(self) -> dict[str, Any]:
        stats = self.store.stats()
        return {
            "status": self._status,
            "collector_mode": self.config.collector.mode,
            "started_at": self._started_at.isoformat(),
            "last_error": self._last_error or None,
            **stats,
        }

    def _build_sinks(self) -> list[object]:
        sinks: list[object] = []
        mode = self.config.export.mode.lower()
        fmt = self.config.export.format.lower()
        if mode in {"file", "both"}:
            sinks.append(DailyFileSink(self.config.export.directory, fmt))
        if mode in {"syslog", "both"} and self.config.export.syslog_target:
            sinks.append(
                SyslogSink(
                    target=self.config.export.syslog_target,
                    port=self.config.export.syslog_port,
                    protocol=self.config.export.syslog_protocol,
                    output_format=fmt,
                )
            )
        return sinks

    def _run_embedded(self) -> None:
        collector = OutboundCollector(
            settings=CollectorSettings(
                ignore_loopback=self.config.collector.ignore_loopback,
                ignore_private=self.config.collector.ignore_private,
                ignore_root=self.config.collector.ignore_root,
                enable_host_enrichment=self.config.collector.enable_host_enrichment,
            ),
            emit=self._ingest_event,
            on_error=self._record_error,
        )
        try:
            collector.run_forever(stop_event=self._stop_event)
        except CollectorUnavailableError as exc:
            self._status = "degraded"
            self._record_error(str(exc))
        except Exception as exc:
            self._status = "degraded"
            self._record_error(f"collector crashed: {exc}")

    def _run_tail(self) -> None:
        path = Path(self.config.collector.log_source_path)
        offset = 0
        while not self._stop_event.is_set():
            if not path.exists():
                time.sleep(self.config.collector.poll_interval_seconds)
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    handle.seek(offset)
                    while not self._stop_event.is_set():
                        line = handle.readline()
                        if not line:
                            offset = handle.tell()
                            break
                        event = self._parse_tail_line(line.strip())
                        if event:
                            self._ingest_event(event)
            except Exception as exc:
                self._status = "degraded"
                self._record_error(f"log tail failed: {exc}")
            time.sleep(self.config.collector.poll_interval_seconds)

    def _parse_tail_line(self, line: str) -> OutboundEvent | None:
        if not line:
            return None
        try:
            if self.config.collector.log_format.lower() == "csv":
                row = next(csv.reader([line]))
                payload = dict(zip(CSV_FIELDS, row, strict=False))
                return OutboundEvent.from_mapping(payload)
            return OutboundEvent.from_mapping(json.loads(line))
        except Exception as exc:
            self._record_error(f"tail parse failed: {exc}")
            return None

    def _record_error(self, message: str) -> None:
        self._last_error = message

    def _ingest_event(self, event: OutboundEvent) -> None:
        self.store.add(event)
        payload = event.to_dict()
        self.broadcaster.publish(payload)
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception as exc:
                self._record_error(f"sink emit failed: {exc}")
