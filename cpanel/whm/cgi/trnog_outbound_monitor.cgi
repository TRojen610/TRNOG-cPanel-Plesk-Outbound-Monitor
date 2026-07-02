#!/usr/bin/env python3
#WHMADDON:trnog_outbound_monitor:TRNOG Outbound Monitor:trnog-outbound-monitor.png
#ACLS:all

from __future__ import annotations

import html
import os
import sys
import urllib.error
import urllib.request

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 15155
CONFIG_PATH = "/etc/trnog-outbound-monitor/config.yaml"
RESELLER_FILE = "/var/cpanel/resellers"


def send_response(status: str, content_type: str, body: str) -> None:
    sys.stdout.write(f"Status: {status}\r\n")
    sys.stdout.write(f"Content-Type: {content_type}\r\n\r\n")
    sys.stdout.write(body)


def is_allowed_user() -> bool:
    user = os.environ.get("REMOTE_USER", "")
    if user == "root":
        return True

    try:
        with open(RESELLER_FILE, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.startswith(f"{user}:"):
                    continue
                permissions = [item.strip() for item in line.split(":", 1)[1].split(",")]
                return "all" in permissions
    except Exception:
        return False
    return False


def parse_service_endpoint() -> tuple[str, int]:
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    if not os.path.exists(CONFIG_PATH):
        return host, port

    in_http = False
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.split("#", 1)[0].rstrip()
                if not line:
                    continue
                if not raw_line[:1].isspace():
                    in_http = line == "http:"
                    continue
                if not in_http or ":" not in line:
                    continue
                key, value = line.strip().split(":", 1)
                cleaned = value.strip().strip("\"'")
                if key == "host" and cleaned:
                    host = cleaned
                if key == "port" and cleaned.isdigit():
                    port = int(cleaned)
    except Exception:
        return DEFAULT_HOST, DEFAULT_PORT
    return host, port


def build_upstream_request() -> urllib.request.Request:
    host, port = parse_service_endpoint()
    path_info = os.environ.get("PATH_INFO") or "/embed/whm"
    query_string = os.environ.get("QUERY_STRING", "")
    upstream = f"http://{host}:{port}{path_info}"
    if query_string:
        upstream = f"{upstream}?{query_string}"

    method = os.environ.get("REQUEST_METHOD", "GET").upper()
    content_length = int(os.environ.get("CONTENT_LENGTH", "0") or "0")
    body = sys.stdin.buffer.read(content_length) if content_length else None

    headers = {
        "User-Agent": "TRNOG-WHM-Proxy/1.0",
        "X-Forwarded-Prefix": f"{os.environ.get('SCRIPT_NAME', '/cgi/trnog_outbound_monitor.cgi')}/",
        "X-Embed-Mode": "whm",
    }
    if os.environ.get("CONTENT_TYPE"):
        headers["Content-Type"] = os.environ["CONTENT_TYPE"]
    if os.environ.get("REMOTE_ADDR"):
        headers["X-Forwarded-For"] = os.environ["REMOTE_ADDR"]

    return urllib.request.Request(upstream, data=body, headers=headers, method=method)


def proxy() -> None:
    if not is_allowed_user():
        send_response(
            "403 Forbidden",
            "text/html; charset=utf-8",
            "<h1>Access denied</h1><p>This interface requires the WHM <code>all</code> ACL.</p>",
        )
        return

    request = build_upstream_request()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            sys.stdout.write(f"Status: {response.status} {response.reason}\r\n")
            for header, value in response.headers.items():
                if header.lower() in {
                    "content-type",
                    "cache-control",
                    "etag",
                    "last-modified",
                }:
                    sys.stdout.write(f"{header}: {value}\r\n")
            sys.stdout.write("\r\n")
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        send_response(
            f"{exc.code} {exc.reason}",
            exc.headers.get("Content-Type", "text/plain; charset=utf-8"),
            body,
        )
    except Exception as exc:
        message = html.escape(str(exc))
        send_response(
            "502 Bad Gateway",
            "text/html; charset=utf-8",
            f"<h1>Service unavailable</h1><p>{message}</p>",
        )


if __name__ == "__main__":
    proxy()
