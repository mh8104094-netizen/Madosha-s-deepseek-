from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _RailwayHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({"ok": True, "service": "x-mind-health-bridge"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def _serve_health_bridge():
    try:
        server = ThreadingHTTPServer(("0.0.0.0", 8080), _RailwayHealthHandler)
        server.serve_forever()
    except OSError:
        # If Railway changes its health port or it is already occupied,
        # never block the primary X-MIND process from starting.
        pass


threading.Thread(target=_serve_health_bridge, name="railway-health-bridge", daemon=True).start()
