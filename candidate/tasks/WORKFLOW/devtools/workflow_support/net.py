import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Problem(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def request(method, url, body=None, token='', timeout=30, key=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if key:
        headers['Idempotency-Key'] = key
    req = urllib.request.Request(url, method=method, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            return response.status, json.loads(response.read(2 * 1024 * 1024))
    except urllib.error.HTTPError as response:
        try:
            value = json.loads(response.read(2 * 1024 * 1024))
        except ValueError:
            value = {'code': 'UPSTREAM_HTTP_ERROR'}
        return response.code, value
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        raise Problem(503, 'TRANSPORT_ERROR') from error


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def dispatch(self):
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if n < 0 or n > 1024 * 1024:
                raise Problem(413, 'BODY_TOO_LARGE')
            body = json.loads(self.rfile.read(n)) if n else {}
            if not isinstance(body, dict):
                raise Problem(400, 'OBJECT_REQUIRED')
            token = self.headers.get('Authorization', '').removeprefix('Bearer ')
            status, value = self.server.app(self.command, self.path, body, token,
                                            self.headers.get('Idempotency-Key'))
            if status == 0:  # Caller requested connection close without a response.
                self.close_connection = True
                return
        except Problem as error:
            status, value = error.status, {'code': error.code}
        except (ValueError, KeyError, TypeError):
            status, value = 400, {'code': 'INVALID_INPUT'}
        except Exception:
            status, value = 500, {'code': 'INTERNAL_ERROR'}
        raw = (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if isinstance(value, str) else 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass


def server(app, port, host='127.0.0.1'):
    instance = ThreadingHTTPServer((host, port), Handler)
    instance.daemon_threads = True
    instance.app = app
    return instance
