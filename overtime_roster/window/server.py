"""Browser mode: a local web server on 127.0.0.1 that serves `web/` and the app's API.

  GET  /                      the page (web/index.html), static files under web/
  POST /api/<method>          JSON {"args": [...]} -> the Api method's JSON reply
  GET  /api/events?token=...  server-sent events: the pushes the window would get

Every API call needs the session token (header X-Overtime-Token, or ?token= for the event stream) that is put in
the URL opened in the browser, and the Host header must be the loopback address: other web pages in the same
browser cannot drive the app.
"""
import json
import mimetypes
import os
import queue
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web')
TYPES = {'.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.html': 'text/html',
         '.woff2': 'font/woff2', '.png': 'image/png', '.svg': 'image/svg+xml', '.json': 'application/json',
         '.txt': 'text/plain'}
QUEUE = 64      # connections waiting to be taken: the page asks for its files at once (Python's 5 left it blank)


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = QUEUE

    def __init__(self, api, host, port=0):
        self.api, self.host = api, host
        self.token = secrets.token_urlsafe(18)
        super().__init__(('127.0.0.1', port), Handler)

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server_address[1]}/?token={self.token}'

    def serve_background(self):
        t = threading.Thread(target=self.serve_forever, daemon=True, name='http')
        t.start()
        return t


class Handler(BaseHTTPRequestHandler):
    server_version = 'OvertimeRoster'

    def log_message(self, fmt, *args):  # quiet
        pass

    def _loopback(self):
        host = (self.headers.get('Host') or '').rsplit(':', 1)[0]
        return host in ('127.0.0.1', 'localhost')

    def _send(self, code, body=b'', ctype='application/json', extra=()):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if not self._loopback():
            return self._send(403, b'{"error":"host"}')
        url = urlparse(self.path)
        if url.path == '/api/events':
            token = parse_qs(url.query).get('token', [''])[0]
            if not secrets.compare_digest(token, self.server.token):
                return self._send(403, b'{"error":"token"}')
            return self._events()
        rel = url.path.lstrip('/') or 'index.html'
        path = os.path.normpath(os.path.join(WEB, rel))
        if not path.startswith(WEB + os.sep) or not os.path.isfile(path):
            return self._send(404, b'not found', 'text/plain')
        with open(path, 'rb') as f:
            body = f.read()
        ext = os.path.splitext(path)[1].lower()
        self._send(200, body, TYPES.get(ext) or mimetypes.guess_type(path)[0] or 'application/octet-stream')

    def do_POST(self):
        if not self._loopback():
            return self._send(403, b'{"error":"host"}')
        if not secrets.compare_digest(self.headers.get('X-Overtime-Token', ''), self.server.token):
            return self._send(403, b'{"error":"token"}')
        url = urlparse(self.path)
        if not url.path.startswith('/api/'):
            return self._send(404, b'{"error":"not found"}')
        name = url.path[len('/api/'):]
        try:
            n = int(self.headers.get('Content-Length') or 0)
            payload = json.loads(self.rfile.read(n) or b'{}') if n else {}
            args = payload.get('args', []) if isinstance(payload, dict) else []
        except ValueError:
            return self._send(400, b'{"error":"bad json"}')
        method = getattr(self.server.api, name, None) if name in self.server.api.EXPOSED else None
        if method is None:
            return self._send(404, json.dumps({'error': f'no method {name}'}).encode())
        reply = method(*args)
        self._send(200, json.dumps(reply).encode())

    def _events(self):
        q = queue.Queue()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.server.host.add_transport(q.put)
        try:
            self.wfile.write(b': hello\n\n')
            self.wfile.flush()
            while True:
                try:
                    text = q.get(timeout=15)
                    self.wfile.write(b'data: ' + text.encode() + b'\n\n')
                except queue.Empty:
                    self.wfile.write(b': ping\n\n')
                self.wfile.flush()
        except (ConnectionError, OSError):
            pass
        finally:
            self.server.host.remove_transport(q.put)
