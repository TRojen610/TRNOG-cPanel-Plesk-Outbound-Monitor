from __future__ import annotations

import ctypes as ct
import ipaddress
import os
import pwd
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
from typing import Callable

from .models import OutboundEvent

BPF_PROGRAM = r"""
#include <uapi/linux/ptrace.h>
#include <uapi/linux/in.h>
#include <linux/ptrace.h>
#include <net/sock.h>
#include <bcc/proto.h>

#define HOST_LEN 256

struct ipv4_event_t {
    u64 ts_us;
    u32 pid;
    u32 uid;
    u32 saddr;
    u32 daddr;
    u16 sport;
    u16 dport;
    char comm[TASK_COMM_LEN];
};

struct ipv6_event_t {
    u64 ts_us;
    u32 pid;
    u32 uid;
    unsigned __int128 saddr;
    unsigned __int128 daddr;
    u16 sport;
    u16 dport;
    char comm[TASK_COMM_LEN];
};

struct host_event_t {
    u32 pid;
    u32 uid;
    u8 source;
    char host[HOST_LEN];
};

BPF_HASH(currsock, u64, struct sock *);
BPF_PERF_OUTPUT(ipv4_events);
BPF_PERF_OUTPUT(ipv6_events);
BPF_PERF_OUTPUT(host_events);

int trace_connect_v4_entry(struct pt_regs *ctx, struct sock *sk) {
    u64 pid_tgid = bpf_get_current_pid_tgid();
    currsock.update(&pid_tgid, &sk);
    return 0;
}

int trace_connect_v4_return(struct pt_regs *ctx) {
    int ret = PT_REGS_RC(ctx);
    u64 pid_tgid = bpf_get_current_pid_tgid();
    struct sock **skpp = currsock.lookup(&pid_tgid);
    if (skpp == 0) {
        return 0;
    }

    if (ret != 0) {
        currsock.delete(&pid_tgid);
        return 0;
    }

    struct sock *sk = *skpp;
    u16 dport = 0, sport = 0;
    u32 saddr = 0, daddr = 0;

    bpf_probe_read_kernel(&sport, sizeof(sport), &sk->__sk_common.skc_num);
    bpf_probe_read_kernel(&dport, sizeof(dport), &sk->__sk_common.skc_dport);
    bpf_probe_read_kernel(&saddr, sizeof(saddr), &sk->__sk_common.skc_rcv_saddr);
    bpf_probe_read_kernel(&daddr, sizeof(daddr), &sk->__sk_common.skc_daddr);

    struct ipv4_event_t evt = {};
    evt.ts_us = bpf_ktime_get_ns() / 1000;
    evt.pid = pid_tgid >> 32;
    evt.uid = bpf_get_current_uid_gid();
    evt.saddr = saddr;
    evt.daddr = daddr;
    evt.sport = sport;
    evt.dport = ntohs(dport);
    bpf_get_current_comm(&evt.comm, sizeof(evt.comm));

    ipv4_events.perf_submit(ctx, &evt, sizeof(evt));
    currsock.delete(&pid_tgid);
    return 0;
}

int trace_connect_v6_entry(struct pt_regs *ctx, struct sock *sk) {
    u64 pid_tgid = bpf_get_current_pid_tgid();
    currsock.update(&pid_tgid, &sk);
    return 0;
}

int trace_connect_v6_return(struct pt_regs *ctx) {
    int ret = PT_REGS_RC(ctx);
    u64 pid_tgid = bpf_get_current_pid_tgid();
    struct sock **skpp = currsock.lookup(&pid_tgid);
    if (skpp == 0) {
        return 0;
    }

    if (ret != 0) {
        currsock.delete(&pid_tgid);
        return 0;
    }

    struct sock *sk = *skpp;
    u16 dport = 0, sport = 0;
    unsigned __int128 saddr = 0, daddr = 0;

    bpf_probe_read_kernel(&sport, sizeof(sport), &sk->__sk_common.skc_num);
    bpf_probe_read_kernel(&dport, sizeof(dport), &sk->__sk_common.skc_dport);
    bpf_probe_read_kernel(&saddr, sizeof(saddr), sk->__sk_common.skc_v6_rcv_saddr.in6_u.u6_addr32);
    bpf_probe_read_kernel(&daddr, sizeof(daddr), sk->__sk_common.skc_v6_daddr.in6_u.u6_addr32);

    struct ipv6_event_t evt = {};
    evt.ts_us = bpf_ktime_get_ns() / 1000;
    evt.pid = pid_tgid >> 32;
    evt.uid = bpf_get_current_uid_gid();
    evt.saddr = saddr;
    evt.daddr = daddr;
    evt.sport = sport;
    evt.dport = ntohs(dport);
    bpf_get_current_comm(&evt.comm, sizeof(evt.comm));

    ipv6_events.perf_submit(ctx, &evt, sizeof(evt));
    currsock.delete(&pid_tgid);
    return 0;
}

int trace_getaddrinfo(struct pt_regs *ctx, const char __user *node) {
    if (node == NULL) {
        return 0;
    }

    struct host_event_t evt = {};
    evt.pid = bpf_get_current_pid_tgid() >> 32;
    evt.uid = bpf_get_current_uid_gid();
    evt.source = 1;
    bpf_probe_read_user_str(&evt.host, sizeof(evt.host), node);
    host_events.perf_submit(ctx, &evt, sizeof(evt));
    return 0;
}

int trace_ssl_set_tlsext_host_name(struct pt_regs *ctx, void *ssl, const char __user *name) {
    if (name == NULL) {
        return 0;
    }

    struct host_event_t evt = {};
    evt.pid = bpf_get_current_pid_tgid() >> 32;
    evt.uid = bpf_get_current_uid_gid();
    evt.source = 2;
    bpf_probe_read_user_str(&evt.host, sizeof(evt.host), name);
    host_events.perf_submit(ctx, &evt, sizeof(evt));
    return 0;
}
"""


class CollectorUnavailableError(RuntimeError):
    """Raised when BCC or required kernel hooks are not available."""


@dataclass(slots=True)
class CollectorSettings:
    ignore_loopback: bool = True
    ignore_private: bool = False
    ignore_root: bool = False
    enable_host_enrichment: bool = True

    @classmethod
    def from_env(cls) -> "CollectorSettings":
        def read_bool(name: str, default: str) -> bool:
            return os.environ.get(name, default).strip().lower() == "yes"

        return cls(
            ignore_loopback=read_bool("IGNORE_LOOPBACK", "yes"),
            ignore_private=read_bool("IGNORE_PRIVATE", "no"),
            ignore_root=read_bool("IGNORE_ROOT", "no"),
            enable_host_enrichment=read_bool("ENABLE_HOST_ENRICHMENT", "yes"),
        )


class HostEvent(ct.Structure):
    _fields_ = [
        ("pid", ct.c_uint),
        ("uid", ct.c_uint),
        ("source", ct.c_ubyte),
        ("host", ct.c_char * 256),
    ]


class OutboundCollector:
    def __init__(
        self,
        settings: CollectorSettings,
        emit: Callable[[OutboundEvent], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._settings = settings
        self._emit = emit
        self._on_error = on_error or (lambda message: None)
        self._hostname = socket.gethostname()
        self._host_cache: dict[int, dict[str, object]] = {}
        self._host_ttl = 20
        self._bpf = None

    def run_forever(self, stop_event: Event | None = None) -> None:
        stop_event = stop_event or Event()
        try:
            from bcc import BPF
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise CollectorUnavailableError(f"BCC import failed: {exc}") from exc

        try:
            self._bpf = BPF(text=BPF_PROGRAM)
            self._attach_probes()
            self._open_buffers()
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise CollectorUnavailableError(f"collector attach failed: {exc}") from exc

        while not stop_event.is_set():
            try:
                self._bpf.perf_buffer_poll(timeout=200)
            except TypeError:
                self._bpf.perf_buffer_poll()
            except KeyboardInterrupt:
                break

    def _attach_probes(self) -> None:
        assert self._bpf is not None
        self._bpf.attach_kprobe(event="tcp_v4_connect", fn_name="trace_connect_v4_entry")
        self._bpf.attach_kretprobe(
            event="tcp_v4_connect",
            fn_name="trace_connect_v4_return",
        )
        self._bpf.attach_kprobe(event="tcp_v6_connect", fn_name="trace_connect_v6_entry")
        self._bpf.attach_kretprobe(
            event="tcp_v6_connect",
            fn_name="trace_connect_v6_return",
        )

        if not self._settings.enable_host_enrichment:
            return

        try:
            self._bpf.attach_uprobe(name="c", sym="getaddrinfo", fn_name="trace_getaddrinfo")
        except Exception:
            pass

        libssl_path = self._find_libssl()
        if not libssl_path:
            return
        try:
            self._bpf.attach_uprobe(
                name=libssl_path,
                sym="SSL_set_tlsext_host_name",
                fn_name="trace_ssl_set_tlsext_host_name",
            )
        except Exception:
            pass

    def _open_buffers(self) -> None:
        assert self._bpf is not None
        self._bpf["ipv4_events"].open_perf_buffer(self._handle_ipv4)
        self._bpf["ipv6_events"].open_perf_buffer(self._handle_ipv6)
        self._bpf["host_events"].open_perf_buffer(self._handle_host)

    def _handle_host(self, _cpu: int, data: int, _size: int) -> None:
        event = ct.cast(data, ct.POINTER(HostEvent)).contents
        pid = int(event.pid)
        source = "dns" if int(event.source) == 1 else "sni"
        host = bytes(event.host).split(b"\x00", 1)[0].decode(errors="replace").strip()
        self._remember_host(pid, host, source)

    def _handle_ipv4(self, _cpu: int, data: int, _size: int) -> None:
        try:
            event = self._bpf["ipv4_events"].event(data)
            payload = {
                "timestamp": datetime.now(timezone.utc),
                "hostname": self._hostname,
                "uid": int(event.uid),
                "user": self._get_username(int(event.uid)),
                "pid": int(event.pid),
                "comm": event.comm.decode(errors="replace").rstrip("\x00"),
                "cmdline": self._get_cmdline(int(event.pid)),
                "family": "ipv4",
                "src_ip": self._ip4_to_str(event.saddr),
                "src_port": int(event.sport),
                "dst_ip": self._ip4_to_str(event.daddr),
                "dst_port": int(event.dport),
            }
            self._emit_payload(payload)
        except Exception as exc:
            self._on_error(f"handle_ipv4_failed: {exc}")

    def _handle_ipv6(self, _cpu: int, data: int, _size: int) -> None:
        try:
            event = self._bpf["ipv6_events"].event(data)
            payload = {
                "timestamp": datetime.now(timezone.utc),
                "hostname": self._hostname,
                "uid": int(event.uid),
                "user": self._get_username(int(event.uid)),
                "pid": int(event.pid),
                "comm": event.comm.decode(errors="replace").rstrip("\x00"),
                "cmdline": self._get_cmdline(int(event.pid)),
                "family": "ipv6",
                "src_ip": self._ip6_to_str(event.saddr),
                "src_port": int(event.sport),
                "dst_ip": self._ip6_to_str(event.daddr),
                "dst_port": int(event.dport),
            }
            self._emit_payload(payload)
        except Exception as exc:
            self._on_error(f"handle_ipv6_failed: {exc}")

    def _emit_payload(self, payload: dict[str, object]) -> None:
        dst_host, dst_host_source = self._get_host_for_pid(int(payload["pid"]))
        if dst_host:
            payload["dst_host"] = dst_host
            payload["dst_host_source"] = dst_host_source
        event = OutboundEvent.from_mapping(payload)
        if self._should_skip(event):
            return
        self._emit(event)

    def _get_username(self, uid: int) -> str:
        try:
            return pwd.getpwuid(uid).pw_name
        except Exception:
            return str(uid)

    def _get_cmdline(self, pid: int) -> str:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as handle:
                data = handle.read().replace(b"\x00", b" ").decode(errors="replace").strip()
                return data if data else ""
        except Exception:
            return ""

    def _remember_host(self, pid: int, host: str, source: str) -> None:
        if not self._settings.enable_host_enrichment:
            return
        if not self._valid_host(host):
            return
        self._host_cache[pid] = {"host": host, "source": source, "ts": time.time()}

    def _get_host_for_pid(self, pid: int) -> tuple[str | None, str | None]:
        self._cleanup_host_cache()
        item = self._host_cache.get(pid)
        if not item:
            return None, None
        return str(item["host"]), str(item["source"])

    def _cleanup_host_cache(self) -> None:
        now = time.time()
        expired = [
            pid
            for pid, value in self._host_cache.items()
            if now - float(value["ts"]) > self._host_ttl
        ]
        for pid in expired:
            self._host_cache.pop(pid, None)

    def _should_skip(self, event: OutboundEvent) -> bool:
        if self._settings.ignore_root and event.uid == 0:
            return True
        if (
            self._settings.ignore_loopback
            and self._is_loopback(event.src_ip)
            and self._is_loopback(event.dst_ip)
        ):
            return True
        if self._settings.ignore_private and self._is_private(event.dst_ip):
            return True
        return False

    def _valid_host(self, host: str) -> bool:
        if not host:
            return False
        host = host.strip()
        if len(host) < 2:
            return False
        if " " in host:
            return False
        if host.startswith("/"):
            return False
        return True

    def _is_loopback(self, value: str) -> bool:
        try:
            return ipaddress.ip_address(value).is_loopback
        except Exception:
            return False

    def _is_private(self, value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
            return address.is_private or address.is_link_local
        except Exception:
            return False

    def _ip4_to_str(self, value: int) -> str:
        return socket.inet_ntop(socket.AF_INET, int(value).to_bytes(4, byteorder="little"))

    def _ip6_to_str(self, raw: object) -> str:
        try:
            if isinstance(raw, (bytes, bytearray)):
                buffer = bytes(raw)
            else:
                try:
                    buffer = bytes(raw)
                except Exception:
                    buffer = int(raw).to_bytes(16, byteorder="big", signed=False)
            if len(buffer) != 16:
                buffer = buffer[:16].ljust(16, b"\x00")
            return socket.inet_ntop(socket.AF_INET6, buffer)
        except Exception:
            return ""

    def _find_libssl(self) -> str | None:
        candidates = [
            "/lib64/libssl.so.3",
            "/lib64/libssl.so.1.1",
            "/usr/lib64/libssl.so.3",
            "/usr/lib64/libssl.so.1.1",
            "/lib/x86_64-linux-gnu/libssl.so.3",
            "/lib/x86_64-linux-gnu/libssl.so.1.1",
            "/usr/lib/x86_64-linux-gnu/libssl.so.3",
            "/usr/lib/x86_64-linux-gnu/libssl.so.1.1",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        try:
            output = subprocess.check_output(
                ["sh", "-c", "ldconfig -p | grep 'libssl.so' | head -n1 | awk '{print $NF}'"],
                text=True,
            ).strip()
            if output and os.path.exists(output):
                return output
        except Exception:
            pass
        return None


def cli_main() -> int:
    log_format = os.environ.get("LOG_FORMAT", "json").strip().lower()

    def emit(event: OutboundEvent) -> None:
        if log_format == "csv":
            print(event.to_csv_line(), flush=True)
        else:
            print(event.to_json_line(), flush=True)

    collector = OutboundCollector(
        settings=CollectorSettings.from_env(),
        emit=emit,
        on_error=lambda message: print(message, file=sys.stderr, flush=True),
    )
    collector.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
