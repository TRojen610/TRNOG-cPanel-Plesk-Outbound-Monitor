from __future__ import annotations

import socket
from pathlib import Path
from threading import Lock

from core.models import OutboundEvent


class DailyFileSink:
    def __init__(self, directory: str, output_format: str = "json") -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._output_format = output_format
        self._lock = Lock()

    def emit(self, event: OutboundEvent) -> None:
        extension = "csv" if self._output_format == "csv" else "jsonl"
        path = self._directory / f"{event.timestamp.date().isoformat()}.{extension}"
        line = event.to_csv_line() if self._output_format == "csv" else event.to_json_line()
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")


class SyslogSink:
    def __init__(
        self,
        target: str,
        port: int = 514,
        protocol: str = "udp",
        output_format: str = "json",
    ) -> None:
        self._target = target
        self._port = port
        self._protocol = protocol
        self._output_format = output_format
        self._lock = Lock()

    def emit(self, event: OutboundEvent) -> None:
        if not self._target:
            return
        payload = event.to_csv_line() if self._output_format == "csv" else event.to_json_line()
        message = payload.encode("utf-8", errors="replace")
        with self._lock:
            if self._protocol == "tcp":
                with socket.create_connection((self._target, self._port), timeout=5) as sock:
                    sock.sendall(message + b"\n")
            else:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.sendto(message, (self._target, self._port))
