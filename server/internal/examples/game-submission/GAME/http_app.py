import json, os, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path

class Problem(Exception):
    def __init__(self,code,status=409): self.code=code; self.status=status

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def handle_request(self):
        parsed=urlparse(self.path)
        try:
            if parsed.path=='/healthz': return self.send(200,{'status':'ok'})
            if parsed.path=='/':
                html=Path(__file__).with_name(self.server.task.lower()+'.html').read_text(encoding='utf-8')
                return self.send(200,html,'text/html; charset=utf-8')
            n=int(self.headers.get('Content-Length','0'))
            if n>1024*1024: raise Problem('TOO_LARGE',413)
            body=json.loads(self.rfile.read(n)) if n else {}
            token=self.headers.get('Authorization','').removeprefix('Bearer ')
            with self.server.lock:
                status,value=self.server.app(self.command,parsed.path,body,token,parse_qs(parsed.query))
            self.send(status,value)
        except Problem as ex: self.send(ex.status,{'code':ex.code})
        except (ValueError,KeyError,TypeError,IndexError): self.send(400,{'code':'INVALID_INPUT'})
        except Exception as ex: self.send(500,{'code':'INTERNAL_ERROR','message':str(ex)[:200]})
    def send(self,status,value,mime='application/json; charset=utf-8'):
        raw=value.encode('utf-8') if isinstance(value,str) else json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

def serve(app,task):
    server=ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler)
    server.lock=threading.RLock();server.app=app;server.task=task;server.serve_forever()
