"""Lightweight HTTP server for live dashboard data refresh.

Serves the dashboard HTML at / and re-reads the data source on each
GET /api/data request, enabling live data updates without page reload.

The server runs in a daemon thread so it doesn't block the MCP process.
Only one server runs at a time; starting a new one stops the previous.
"""

from __future__ import annotations

import json
import socket
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .data_utils import load_dataframe

# Module-level state: one active server at a time
_active_server: dict[str, Any] | None = None
_lock = threading.Lock()


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler serving dashboard HTML and live data API."""

    # Injected via partial/closure
    dashboard_html: str = ""
    data_source: str = ""

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "":
            self._serve_html()
        elif self.path == "/api/data":
            self._serve_data()
        else:
            self.send_error(404, "Not Found")

    def _serve_html(self) -> None:
        content = self.dashboard_html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(content)

    def _serve_data(self) -> None:
        try:
            df = load_dataframe(self.data_source)
            records = df.to_dict(orient="records")
            body = json.dumps(records, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._add_cors_headers()
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            error_body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error_body)))
            self._add_cors_headers()
            self.end_headers()
            self.wfile.write(error_body)

    def _add_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress all log output — stderr is the MCP transport channel."""
        pass


def _find_open_port(start: int, max_tries: int = 20) -> int:
    """Find an open port starting from *start*, trying up to *max_tries* ports."""
    for offset in range(max_tries):
        port = start + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise OSError(f"No open port found in range {start}–{start + max_tries - 1}")


def start_server(
    html: str,
    data_source: str,
    port: int = 8050,
    host: str = "127.0.0.1",
) -> dict[str, Any]:
    """Start the dashboard HTTP server in a daemon thread.

    Stops any previously running server first (one-at-a-time model).
    Auto-increments port if the requested one is in use.

    Returns: {"port": int, "url": str}
    """
    global _active_server

    with _lock:
        # Stop any existing server
        if _active_server is not None:
            _stop_active_server()

        actual_port = _find_open_port(port)

        # Create handler class with injected data
        handler = type(
            "Handler",
            (DashboardRequestHandler,),
            {"dashboard_html": html, "data_source": data_source},
        )

        server = HTTPServer((host, actual_port), handler)

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        _active_server = {
            "server": server,
            "thread": thread,
            "port": actual_port,
            "host": host,
        }

    return {"port": actual_port, "url": f"http://{host}:{actual_port}"}


def stop_server(port: int | None = None) -> bool:
    """Stop the active dashboard server.

    Args:
        port: If provided, only stop if the active server is on this port.

    Returns True if a server was stopped, False if none was running.
    """
    global _active_server

    with _lock:
        if _active_server is None:
            return False
        if port is not None and _active_server["port"] != port:
            return False
        return _stop_active_server()


def _stop_active_server() -> bool:
    """Stop the active server (caller must hold _lock). Returns True."""
    global _active_server
    if _active_server is None:
        return False
    try:
        _active_server["server"].shutdown()
    except Exception:
        pass
    _active_server = None
    return True


def get_active_server() -> dict[str, Any] | None:
    """Return info about the active server, or None."""
    with _lock:
        if _active_server is None:
            return None
        return {
            "port": _active_server["port"],
            "host": _active_server["host"],
            "url": f"http://{_active_server['host']}:{_active_server['port']}",
        }
