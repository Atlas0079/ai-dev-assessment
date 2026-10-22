"""Public smoke test against a candidate's already-running app and local virtual business service."""
import argparse
import os
import uuid
from .net import request


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:8080')
    p.add_argument('--business-url', default='http://127.0.0.1:8091')
    p.add_argument('--order', required=True)
    p.add_argument('--token-env', default='WORKFLOW_USER_TOKEN')
    a = p.parse_args()
    token = os.environ.get(a.token_env)
    if not token:
        p.error('Set the demo user token in ' + a.token_env)
    def call(method, url, body=None, key=None):
        status, result = request(method, url, body, token, timeout=300, key=key)
        if status != 200:
            raise RuntimeError(f'HTTP{status}: {result}')
        return result
    before = call('GET', a.business_url+'/v1/tickets')['tickets']
    sid = call('POST', a.url+'/sessions', {})['session_id']
    draft = call('POST', a.url+f'/sessions/{sid}/messages', {'message':f'订单 {a.order} 服务没有完成，我想申请售后。'})
    if draft.get('status') != 'awaiting_confirmation':
        raise RuntimeError('Expected awaiting_confirmation: '+str(draft))
    if call('GET',a.business_url+'/v1/tickets')['tickets'] != before:
        raise RuntimeError('Ticket created before confirmation')
    key = uuid.uuid4().hex
    body = {'draft_id':draft['draft']['draft_id']}
    result = call('POST',a.url+f'/sessions/{sid}/confirm',body,key)
    replay = call('POST',a.url+f'/sessions/{sid}/confirm',body,key)
    tickets = call('GET',a.business_url+'/v1/tickets')['tickets']
    if result.get('status') != 'completed' or result != replay or len(tickets) != len(before)+1:
        raise RuntimeError('Completion / idempotency check failed')
    if result.get('ticket',{}).get('ticket_id') != tickets[-1]['ticket_id']:
        raise RuntimeError('Returned ticket ID is not the stored ID')
    print('PASS: explicit confirmation, real virtual ticket, idempotent replay. This smoke test is not full acceptance.')


if __name__ == '__main__':
    main()
