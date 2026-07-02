from __future__ import annotations

from queue import Empty, Queue
from threading import Lock
from typing import Any


class EventBroadcaster:
    def __init__(self, queue_size: int = 256) -> None:
        self._queue_size = queue_size
        self._subscribers: list[Queue[dict[str, Any]]] = []
        self._lock = Lock()

    def subscribe(self) -> Queue[dict[str, Any]]:
        queue: Queue[dict[str, Any]] = Queue(maxsize=self._queue_size)
        with self._lock:
            self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: Queue[dict[str, Any]]) -> None:
        with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def publish(self, payload: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except Exception:
                try:
                    queue.get_nowait()
                except Empty:
                    pass
                try:
                    queue.put_nowait(payload)
                except Exception:
                    pass
