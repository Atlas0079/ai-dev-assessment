"""Same-origin HR HTTP service; no endpoint executes uploaded host code."""
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import traceback
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .hr_jobs import MAX_UPLOAD, RequestError, STATES
from .hr_report import pdf_bytes, report_view
from .storage import ROOT

WEB = ROOT / 'web'


class ServiceLock:
    def __init__(self, root):
        self.stream = (root / '.service.lock').open('a+b')
        self.stream.seek(0, 2)
        if self.stream.tell() == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError('该数据目录已有服务运行，请使用单一服务实例。')

    def close(self):
        self.stream.close()


class HRServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store, password='', secure_cookie=False):
        if address[0] not in {'127.0.0.1', 'localhost', '::1'} and not password:
            raise ValueError('内网监听需要设置 HR_ACCESS_PASSWORD。')
        self.store = store
        self.password = password
        self.secure_cookie = secure_cookie
        self.local_only = address[0] in {'127.0.0.1', 'localhost', '::1'}
        self.login_failures = {}
        self.service_lock = ServiceLock(store.root)
        try:
            key = store.root / '.session-key'
            if not key.exists():
                descriptor = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(secrets.token_bytes(32))
            self.session_key = hmac.new(key.read_bytes(), password.encode(), hashlib.sha256).digest()
            super().__init__(address, Handler)
            store.recover_interrupted()
        except Exception:
            if hasattr(self, 'socket'):
                super().server_close()
            self.service_lock.close()
            raise

    def session(self):
        value = str(int(time.time())) + '.' + secrets.token_hex(16)
        return value + '.' + hmac.new(self.session_key, value.encode(), hashlib.sha256).hexdigest()

    def authenticated(self, cookie_header):
        if not self.password:
            return True
        try:
            jar = cookies.SimpleCookie(cookie_header or '')
            value = jar['hr_session'].value
            created, random, signature = value.split('.')
            if not 0 <= time.time() - int(created) <= 8 * 3600:
                return False
            expected = hmac.new(self.session_key, (created + '.' + random).encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, expected)
        except (KeyError, ValueError, cookies.CookieError):
            return False

    def server_close(self):
        super().server_close()
        self.service_lock.close()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(45)

    def log_message(self, *args):
        pass

    def respond(self, status, value, kind='application/json; charset=utf-8', extra=None):
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8') if isinstance(value, (dict, list)) else value
        if isinstance(raw, str):
            raw = raw.encode('utf-8')
        self.send_response(status)
        headers = {'Content-Type': kind, 'Content-Length': str(len(raw)), 'Cache-Control': 'no-store',
                   'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin',
                   'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"}
        headers.update(extra or {})
        for key, item in headers.items():
            self.send_header(key, item)
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def body(self, maximum):
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            raise RequestError('请求长度无效。')
        if self.headers.get('Transfer-Encoding') or length < 0:
            raise RequestError('请求格式无效。')
        if length > maximum:
            self.close_connection = True
            raise RequestError('文件超过允许大小。', 413)
        value = self.rfile.read(length)
        if len(value) != length:
            raise RequestError('上传未完成，请重试。')
        return value

    def same_origin(self):
        origin = urlsplit(self.headers.get('Origin', ''))
        if origin.scheme not in {'http', 'https'} or origin.netloc != self.headers.get('Host'):
            raise RequestError('请从服务页面发起操作。', 403)

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def dispatch(self):
        try:
            host = urlsplit('http://' + self.headers.get('Host', '')).hostname
            if self.server.local_only and host not in {'127.0.0.1', 'localhost', '::1'}:
                raise RequestError('访问地址无效。', 403)
            parts = [unquote(p) for p in urlsplit(self.path).path.split('/') if p]
            if self.command == 'POST':
                self.same_origin()
            if self.command == 'GET' and parts in [[], ['app.css'], ['app.js']]:
                name = 'index.html' if not parts else parts[0]
                kind = {'index.html': 'text/html; charset=utf-8', 'app.css': 'text/css; charset=utf-8',
                        'app.js': 'text/javascript; charset=utf-8'}[name]
                return self.respond(200, (WEB / name).read_bytes(), kind)
            if parts == ['api', 'session'] and self.command == 'GET':
                return self.respond(200, {'authenticated': self.server.authenticated(self.headers.get('Cookie')),
                                          'loginRequired': bool(self.server.password)})
            if parts == ['api', 'login'] and self.command == 'POST':
                try:
                    value = json.loads(self.body(4096))
                    supplied = value['password']
                    if not isinstance(supplied, str):
                        raise ValueError()
                except (ValueError, KeyError, TypeError):
                    raise RequestError('请填写访问口令。')
                key = self.client_address[0]
                with self.server.store.lock:
                    stamp, count = self.server.login_failures.get(key, (time.time(), 0))
                    if time.time() - stamp > 60:
                        stamp, count = time.time(), 0
                    if count >= 8:
                        raise RequestError('尝试次数过多，请稍后重试。', 429)
                    if not hmac.compare_digest(supplied.encode(), self.server.password.encode()):
                        self.server.login_failures[key] = (stamp, count + 1)
                        raise RequestError('访问口令不正确。', 401)
                    self.server.login_failures.pop(key, None)
                cookie = 'hr_session=' + self.server.session() + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'
                if self.server.secure_cookie:
                    cookie += '; Secure'
                return self.respond(200, {'ok': True}, extra={'Set-Cookie': cookie})
            if not self.server.authenticated(self.headers.get('Cookie')):
                raise RequestError('请先登录。', 401)
            if parts == ['api', 'logout'] and self.command == 'POST':
                self.body(4096)
                return self.respond(200, {'ok': True}, extra={'Set-Cookie': 'hr_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
            if parts == ['api', 'releases'] and self.command == 'GET':
                return self.respond(200, self.server.store.release_list())
            if parts == ['api', 'status'] and self.command == 'GET':
                from .catalog import QUESTIONS
                blocked = [item for task in QUESTIONS if (item := self.server.store.readiness(task))]
                return self.respond(200, {'blocked': blocked, 'taskCount': len(QUESTIONS)})
            if parts == ['api', 'jobs'] and self.command == 'GET':
                return self.respond(200, [self.public_job(j) for j in self.server.store.list()])
            if parts == ['api', 'jobs'] and self.command == 'POST':
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/zip':
                    raise RequestError('请选择 ZIP 文件。', 415)
                try:
                    filename = unquote(self.headers.get('X-Submission-Filename', ''), errors='strict')
                except UnicodeError as error:
                    raise RequestError('答案文件名无法读取，请按题面要求命名后重新上传。') from error
                job, created = self.server.store.submit(self.body(MAX_UPLOAD), filename,
                                                         self.headers.get('X-Release-Version', ''))
                return self.respond(201 if created else 200, self.public_job(job))
            if len(parts) >= 3 and parts[:2] == ['api', 'jobs']:
                job = self.server.store.get(parts[2])
                current_attempt = job['attempt']
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if 'attempt' in query:
                    values = query['attempt']
                    if len(values) != 1 or not re.fullmatch(r'[1-9][0-9]{0,5}', values[0]):
                        raise RequestError('执行轮次无效。')
                    job = self.server.store.get_attempt(job['id'], int(values[0]))
                if len(parts) == 3 and self.command == 'GET':
                    value = self.public_job(job)
                    value['currentAttempt'] = current_attempt
                    return self.respond(200, {'job': value, 'report': report_view(self.server.store, job)})
                if len(parts) == 4 and parts[3] == 'retry' and self.command == 'POST':
                    if 'attempt' in query:
                        raise RequestError('请从当前记录重试。', 409)
                    self.body(4096)
                    return self.respond(200, self.public_job(self.server.store.retry(job['id'])))
                if len(parts) == 4 and parts[3] == 'report.pdf' and self.command == 'GET':
                    if job['state'] in {'QUEUED', 'RUNNING'}:
                        raise RequestError('评测尚未结束，请稍后下载报告。', 409)
                    raw = pdf_bytes(report_view(self.server.store, job))
                    filename = job['candidateId'] + '_v' + str(job['submissionVersion'] or 0) + '.pdf'
                    return self.respond(200, raw, 'application/pdf',
                        {'Content-Disposition': 'attachment; filename="assessment-report.pdf"; filename*=UTF-8\'\'' + quote(filename, safe='')})
                if len(parts) == 6 and parts[3] == 'evidence' and self.command == 'GET':
                    task, name = parts[4:]
                    if task not in job['results'] or not re.fullmatch(r'EV-[A-Za-z0-9-]+\.json', name):
                        raise RequestError('证据不存在。', 404)
                    source = self.server.store._folder(job['id']) / job['results'][task]
                    path = source.parent / 'evidence' / name
                    if not path.is_file():
                        raise RequestError('证据不存在。', 404)
                    return self.respond(200, path.read_bytes(), 'application/json; charset=utf-8')
            if len(parts) == 4 and parts[:2] == ['api', 'packages'] and self.command == 'GET':
                path = self.server.store.release_file(parts[2], parts[3])
                return self.respond(200, path.read_bytes(), 'application/zip',
                                    {'Content-Disposition': 'attachment; filename="' + path.name + '"'})
            raise RequestError('页面或记录不存在。', 404)
        except RequestError as error:
            self.respond(error.status, {'message': str(error)})
        except Exception:
            number = secrets.token_hex(8)
            with (self.server.store.root / 'http-errors.log').open('a', encoding='utf-8') as stream:
                stream.write(number + '\n' + traceback.format_exc() + '\n')
            self.respond(500, {'message': '服务暂不可用，请联系技术人员。故障编号：' + number})

    def public_job(self, job):
        value = dict(job)
        value.pop('results', None)
        value['stateLabel'] = STATES[job['state']]
        value['hasFailures'] = any(c['status'] == 'FAIL' for r in self.server.store.results(job) for c in r['cases'])
        value['canRetry'] = job['state'] in {'PLATFORM_BLOCKED', 'REVIEW_REQUIRED'}
        return value
