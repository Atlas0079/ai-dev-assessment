"""Public ORDER smoke cases. No internal evaluator or hidden fixtures."""
import argparse
import sys
import uuid
from net import request, Problem


def check(task, url):
    def call(method, path, body=None, token='', key=None):
        status, value = request(method, url.rstrip('/') + path, body, token, key=key)
        if status != 200:
            raise AssertionError(f'{method} {path}: expected HTTP200, got {status}')
        if isinstance(value, dict) and value.get('code') == 0 and 'data' in value:
            value = value['data']
        return value
    def expect(condition, message):
        if not condition:
            raise AssertionError(message)
    expect(call('GET', '/healthz').get('status') == 'ok', 'health status must be ok')
    print('PASS PUBLIC-HEALTH')
    customer = call('POST', '/v1/demo-login', {'account': 'customer1'})['token']
    provider = call('POST', '/v1/demo-login', {'account': 'provider1'})['token']
    order = call('POST', '/v1/orders', {'serviceId': 's1'}, customer)
    expect(order['status'] == 'PENDING', 'new order must be pending')
    print('PASS PUBLIC-ORDER-CREATE')
    path = '/v1/orders/' + order['id']
    call('POST', path + '/accept', {'note': '公开接单样例'}, provider, uuid.uuid4().hex)
    completed = call('POST', path + '/complete', {'note': '公开完成样例'}, provider, uuid.uuid4().hex)
    expect(completed['status'] == 'COMPLETED' and completed['version'] == 2, 'expected completed order, version=2')
    expect(call('GET', path, token=customer) == completed, 'readback must match completed order')
    print('PASS PUBLIC-ORDER-COMPLETE')
    print('Public smoke only; passing does not imply full acceptance. Virtual test data was created.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('task', choices=['ORDER'])
    p.add_argument('--url', default='http://127.0.0.1:8080')
    a = p.parse_args()
    try:
        check(a.task, a.url)
    except (Problem, AssertionError, KeyError, TypeError, ValueError) as error:
        print('PUBLIC CHECK NOT PASSED: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
