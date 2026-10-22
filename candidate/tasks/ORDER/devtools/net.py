import json
import urllib.error
import urllib.request


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
