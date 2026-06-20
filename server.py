"""HTTP server so the iOS Jarvis Remote app can send text commands to the Brain.

Listens on PORT (default 8765) on all interfaces.
One endpoint: POST /ask  {"text": "your message"}  -> {"reply": "..."}
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8765
_brain = None
_lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/ask":
            self._respond(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except Exception:
            self._respond(400, {"error": "bad json"})
            return
        text = (data.get("text") or "").strip()
        if not text:
            self._respond(400, {"error": "empty text"})
            return
        if _brain is None:
            self._respond(503, {"error": "brain not ready"})
            return
        with _lock:
            reply = _brain.ask(text)
        self._respond(200, {"reply": reply})

    def _respond(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # silence default HTTP logging


def start(brain):
    global _brain
    _brain = brain
    httpd = HTTPServer(("", PORT), _Handler)
    t = threading.Thread(target=httpd.serve_forever, name="jarvis-http", daemon=True)
    t.start()
    return httpd
