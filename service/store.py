from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

from core.models import OutboundEvent


@dataclass(slots=True)
class EventQuery:
    window_seconds: int = 3600
    user: str = ""
    dst_ip: str = ""
    port: int | None = None
    family: str = ""
    search: str = ""


class EventStore:
    def __init__(self, max_events: int) -> None:
        self._events: deque[OutboundEvent] = deque(maxlen=max_events)
        self._lock = Lock()
        self._ingested_events = 0
        self._last_event_at: datetime | None = None

    def add(self, event: OutboundEvent) -> None:
        with self._lock:
            self._events.append(event)
            self._ingested_events += 1
            self._last_event_at = event.timestamp

    def summary(self, query: EventQuery) -> dict[str, object]:
        events = self._filtered(query)
        return {
            "window_seconds": query.window_seconds,
            "total_events": len(events),
            "unique_users": len({event.user for event in events}),
            "unique_destinations": len({event.dst_ip for event in events}),
            "unique_ports": len({event.dst_port for event in events}),
            "last_event_at": events[0].timestamp.isoformat() if events else None,
            "ingested_events": self._ingested_events,
        }

    def events(self, query: EventQuery, limit: int) -> list[OutboundEvent]:
        return self._filtered(query)[:limit]

    def top_destinations(self, query: EventQuery, limit: int) -> list[dict[str, object]]:
        counts: Counter[tuple[str, str | None, int]] = Counter()
        for event in self._filtered(query):
            counts[(event.dst_ip, event.dst_host, event.dst_port)] += 1
        return [
            {
                "dst_ip": dst_ip,
                "dst_host": dst_host,
                "dst_port": dst_port,
                "count": count,
            }
            for (dst_ip, dst_host, dst_port), count in counts.most_common(limit)
        ]

    def top_users(self, query: EventQuery, limit: int) -> list[dict[str, object]]:
        counts = Counter(event.user for event in self._filtered(query))
        return [{"user": user, "count": count} for user, count in counts.most_common(limit)]

    def top_ports(self, query: EventQuery, limit: int) -> list[dict[str, object]]:
        counts = Counter(event.dst_port for event in self._filtered(query))
        return [{"port": port, "count": count} for port, count in counts.most_common(limit)]

    def stats(self) -> dict[str, object]:
        with self._lock:
            return {
                "ingested_events": self._ingested_events,
                "buffered_events": len(self._events),
                "last_event_at": self._last_event_at.isoformat() if self._last_event_at else None,
            }

    def _filtered(self, query: EventQuery) -> list[OutboundEvent]:
        with self._lock:
            snapshot = list(self._events)

        search = query.search.strip().lower()
        user = query.user.strip().lower()
        dst_ip = query.dst_ip.strip().lower()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=query.window_seconds)

        events = []
        for event in snapshot:
            if event.timestamp < cutoff:
                continue
            if user and event.user.lower() != user:
                continue
            if dst_ip and event.dst_ip.lower() != dst_ip:
                continue
            if query.port is not None and event.dst_port != query.port:
                continue
            if query.family and event.family.lower() != query.family.lower():
                continue
            if search and not self._matches_search(event, search):
                continue
            events.append(event)

        events.sort(key=lambda item: item.timestamp, reverse=True)
        return events

    def _matches_search(self, event: OutboundEvent, search: str) -> bool:
        haystack = " ".join(
            [
                event.user,
                event.comm,
                event.cmdline,
                event.src_ip,
                event.dst_ip,
                event.dst_host or "",
            ]
        ).lower()
        return search in haystack
