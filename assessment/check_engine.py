"""Evidence only. A passed check is not a quality score."""
import json
import time
import uuid
import urllib.request
import urllib.error
from collections import Counter
from .storage import save


class Unknown(Exception):
    """A prerequisite or transport failure prevents a business conclusion."""


def expect(condition, message='断言未通过'):
    if not condition:
        raise AssertionError(message)


def redact(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if 'token' in k.lower() else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class Client:
    def __init__(self, url, folder):
        self.url = url.rstrip('/'); self.folder = folder; self.evidence = []

    def record(self, value):
        eid = 'EV-' + uuid.uuid4().hex
        save(self.folder / (eid + '.json'), redact(value))
        self.evidence.append(eid)
        return eid

    def call(self, method, path, body=None, token=None, key=None):
        headers = {'Content-Type': 'application/json'}
        if token: headers['Authorization'] = 'Bearer ' + token
        if key: headers['Idempotency-Key'] = key
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
        event = {'method': method, 'path': path, 'request': body, 'idempotencyKey': key}
        start = time.monotonic()
        try:
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    code = response.status; raw = response.read(2 * 1024 * 1024 + 1)
            except urllib.error.HTTPError as response:
                code = response.code; raw = response.read(2 * 1024 * 1024 + 1)
            event.update(status=code, durationMs=round((time.monotonic()-start)*1000))
            if len(raw) > 2 * 1024 * 1024:
                event['error'] = '响应超过2MiB'; self.record(event)
                raise AssertionError('响应超过2MiB')
            try: out = json.loads(raw)
            except ValueError:
                event['responseText'] = raw.decode(errors='replace')[:2000]; self.record(event)
                raise AssertionError('接口未返回JSON')
            event['response'] = out; self.record(event)
            return code, out['data'] if isinstance(out, dict) and out.get('code') == 0 and 'data' in out else out
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            event['transportError'] = str(error); self.record(event)
            raise Unknown('连接失败或超时，需区分环境与应用原因：' + str(error)) from error


class Suite:
    def __init__(self, client, folder):
        self.client = client; self.folder = folder; self.cases = []

    def check(self, id, title, fn, dimension='业务规则'):
        if any(c['id'] == id for c in self.cases):
            raise ValueError('重复用例ID: ' + id)
        start = time.monotonic(); before = len(self.client.evidence)
        status = 'PASS'; detail = '本用例的断言通过'
        try: fn()
        except AssertionError as e: status = 'FAIL'; detail = str(e)
        except Unknown as e: status = 'NOT_RUN'; detail = str(e)
        except Exception as e: status = 'ERROR'; detail = type(e).__name__ + ': ' + str(e)
        self.cases.append(dict(id=id, title=title, dimension=dimension, status=status, detail=detail,
                              durationMs=round((time.monotonic()-start)*1000), evidenceIds=self.client.evidence[before:]))
        save(self.folder / 'cases.json', self.cases)

    def summary(self):
        return {s: sum(c['status'] == s for c in self.cases) for s in ('PASS','FAIL','NOT_RUN','ERROR')}
