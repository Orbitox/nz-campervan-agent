"""HTTP Web Server & JSON API for the KiwiCamp Interactive 28-Day Website.

Generates `web/itinerary_data.json` and `web/a2ui_surface.json` on startup using
`generate_interactive_itinerary_website` and serves the static interactive web
application alongside `/api/itinerary` and `/api/health` endpoints.
"""

from __future__ import annotations

import argparse
import http.server
import json
import logging
import os
import socketserver
from pathlib import Path
from typing import Any

from app.observability.telemetry import configure_observability
from app.tools.nz_campervan_tools import generate_interactive_itinerary_website

logger = configure_observability(service_name="kiwicamp-web-server")


class KiwiCampRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serves `web/` static files plus `/api/itinerary` and `/api/health` JSON routes."""

    def __init__(self, *args: Any, directory: str = "web", **kwargs: Any) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json({"status": "healthy", "service": "kiwicamp-web", "days": 28})
            return
        if self.path == "/api/itinerary":
            data_file = Path(self.directory) / "itinerary_data.json"
            if data_file.exists():
                self._send_raw_json(data_file.read_text(encoding="utf-8"))
                return
        super().do_GET()

    def _send_json(self, payload: Any) -> None:
        self._send_raw_json(json.dumps(payload, ensure_ascii=False))

    def _send_raw_json(self, raw_json: str) -> None:
        encoded = raw_json.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_server(host: str = "0.0.0.0", port: int = 8080, web_dir: str = "web") -> None:
    """Compiles the latest 28-day itinerary JSON and starts the HTTP server."""
    generate_interactive_itinerary_website(output_directory=web_dir)

    handler = lambda *args, **kwargs: KiwiCampRequestHandler(
        *args, directory=web_dir, **kwargs
    )
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), handler) as httpd:
        logger.info("KiwiCamp Interactive Website running at http://%s:%d", host, port)
        httpd.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serve KiwiCamp Interactive Website")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8080")),
        help="Port to bind HTTP server",
    )
    parser.add_argument(
        "--web-dir",
        type=str,
        default="web",
        help="Path to the web directory",
    )
    parsed = parser.parse_args()
    run_server(port=parsed.port, web_dir=parsed.web_dir)
