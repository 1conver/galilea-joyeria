"""Función de Vercel: recibe /api/* y lo pasa a api_core (la misma API que usa server.py)."""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from urllib.parse import urlparse, parse_qs

CURRENT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(CURRENT_DIR)
for folder in (ROOT_DIR, CURRENT_DIR):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import api_core


class handler(BaseHTTPRequestHandler):

    def _send(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        if payload is not None:
            self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            return {}

    def _dispatch(self):
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        body = self._body() if self.command in ("POST", "PUT", "DELETE") else {}
        status, payload = api_core.dispatch(self.command, parsed.path, query, body, dict(self.headers.items()))
        self._send(status, payload)

    def do_OPTIONS(self):
        self._send(200, None)

    do_GET = do_POST = do_PUT = do_DELETE = _dispatch
