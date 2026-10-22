"""Assessment-owned DeepSeek gateway. Upstream credential never reaches submissions."""
import argparse
import copy
import os
import secrets
import threading
import time
import json
from pathlib import Path
from .net import Problem, request, server
from .configuration import effective_config


class Gateway:
    def __init__(self, api_key, access_token, max_calls=200, upstream=None, events_file=None):
        self.api_key, self.access_token = api_key, access_token
        self.max_calls, self.events = max_calls, []
        self.lock = threading.Lock()
        self.upstream = upstream  # Dependency injection for local tests only, not a public option.
        self.events_file = Path(events_file) if events_file else None
        self.config = effective_config()

    def __call__(self, method, path, body, token, key):
        if method == 'GET' and path == '/healthz':
            return 200, {'status': 'ok'}
        if method != 'POST' or path != '/chat/completions':
            raise Problem(404, 'NOT_FOUND')
        if not secrets.compare_digest(token, self.access_token):
            raise Problem(401, 'UNAUTHORIZED')
        model = self.config['llm']['model']
        if body.get('model') != model:
            raise Problem(400, 'MODEL_MISMATCH')
        if body.get('stream'):
            raise Problem(400, 'STREAM_NOT_SUPPORTED')
        with self.lock:
            if len(self.events) >= self.max_calls:
                raise Problem(429, 'ASSESSMENT_BUDGET_EXCEEDED')
            event = {'model': model, 'status': 'STARTED'}
            self.events.append(event)
        # Fix evaluation settings and bound output; never forward arbitrary destinations or headers.
        payload = {k: copy.deepcopy(body[k]) for k in ('model', 'messages', 'tools', 'tool_choice') if k in body}
        payload.update(thinking={'type': 'disabled'}, max_tokens=2048, stream=False)
        start = time.monotonic()
        try:
            status, result = (self.upstream(payload) if self.upstream else
                              request('POST', self.config['llm']['base_url'].rstrip('/') + '/chat/completions',
                                      payload, self.api_key, timeout=self.config['limits']['model_timeout_seconds']))
            event.update(status=status, usage=result.get('usage', {}))
            if status != 200:
                return status, {'code': 'MODEL_UPSTREAM_ERROR'}
            return status, result
        except Problem:
            event['status'] = 'TRANSPORT_ERROR'
            raise
        finally:
            with self.lock:
                event['durationMs'] = round((time.monotonic() - start) * 1000)
                if self.events_file:
                    self.events_file.parent.mkdir(parents=True, exist_ok=True)
                    temporary = self.events_file.with_suffix('.tmp')
                    temporary.write_text(json.dumps({'mode': 'fixture' if self.upstream else 'real-deepseek', 'calls': self.events}, ensure_ascii=False, indent=2), encoding='utf-8')
                    os.replace(temporary, self.events_file)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8092)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--events-file', type=Path, help='Evaluator-owned model usage evidence, never supplied by candidates')
    a = p.parse_args()
    api_key, access = os.environ.get('DEEPSEEK_API_KEY'), os.environ.get('WORKFLOW_GATEWAY_TOKEN')
    if not api_key or not access:
        p.error('Set DEEPSEEK_API_KEY and WORKFLOW_GATEWAY_TOKEN in the environment')
    server(Gateway(api_key, access, events_file=a.events_file), a.port, a.host).serve_forever()
