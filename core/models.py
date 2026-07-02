from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Any, Mapping

CSV_FIELDS = (
    "timestamp",
    "hostname",
    "uid",
    "user",
    "pid",
    "comm",
    "cmdline",
    "family",
    "src_ip",
    "src_port",
    "dst_ip",
    "dst_port",
    "dst_host",
    "dst_host_source",
)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        timestamp = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        timestamp = datetime.fromisoformat(text)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


@dataclass(slots=True)
class OutboundEvent:
    timestamp: datetime
    hostname: str
    uid: int
    user: str
    pid: int
    comm: str
    cmdline: str
    family: str
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    dst_host: str | None = None
    dst_host_source: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "OutboundEvent":
        return cls(
            timestamp=_parse_timestamp(data["timestamp"]),
            hostname=str(data.get("hostname", "")),
            uid=int(data.get("uid", 0)),
            user=str(data.get("user", "")),
            pid=int(data.get("pid", 0)),
            comm=str(data.get("comm", "")),
            cmdline=str(data.get("cmdline", "")),
            family=str(data.get("family", "")),
            src_ip=str(data.get("src_ip", "")),
            src_port=int(data.get("src_port", 0)),
            dst_ip=str(data.get("dst_ip", "")),
            dst_port=int(data.get("dst_port", 0)),
            dst_host=str(data["dst_host"]) if data.get("dst_host") else None,
            dst_host_source=(
                str(data["dst_host_source"]) if data.get("dst_host_source") else None
            ),
        )

    @classmethod
    def from_json_line(cls, line: str) -> "OutboundEvent":
        return cls.from_mapping(json.loads(line))

    @classmethod
    def from_csv_line(cls, line: str) -> "OutboundEvent":
        row = next(csv.reader([line]))
        data = dict(zip(CSV_FIELDS, row, strict=False))
        return cls.from_mapping(data)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "hostname": self.hostname,
            "uid": self.uid,
            "user": self.user,
            "pid": self.pid,
            "comm": self.comm,
            "cmdline": self.cmdline,
            "family": self.family,
            "src_ip": self.src_ip,
            "src_port": self.src_port,
            "dst_ip": self.dst_ip,
            "dst_port": self.dst_port,
        }
        if self.dst_host:
            payload["dst_host"] = self.dst_host
        if self.dst_host_source:
            payload["dst_host_source"] = self.dst_host_source
        return payload

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def to_csv_line(self) -> str:
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                self.timestamp.astimezone(timezone.utc).isoformat(),
                self.hostname,
                self.uid,
                self.user,
                self.pid,
                self.comm,
                self.cmdline,
                self.family,
                self.src_ip,
                self.src_port,
                self.dst_ip,
                self.dst_port,
                self.dst_host or "",
                self.dst_host_source or "",
            ]
        )
        return buffer.getvalue().strip("\r\n")
