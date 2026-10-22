"""Public GAME smoke cases. No internal evaluator or hidden fixtures."""
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
    a = call('POST', '/v1/rooms', {'displayName': '公开样例A'})
    path = '/v1/rooms/' + a['roomId']
    b = call('POST', path + '/join', {'displayName': '公开样例B'})
    for player in (a, b):
        call('POST', path + '/ready', {'ready': True, 'requestId': uuid.uuid4().hex}, player['playerToken'])
    game = call('POST', path + '/start', {'requestId': uuid.uuid4().hex}, a['playerToken'])
    expect(game['status'] == 'PLAYING' and len(game['hand']) == 7, 'expected a playing game with seven own cards')
    expect(game['currentPlayerId'] == a['playerId'], 'host should start')
    print('PASS PUBLIC-GAME-START')
    action = {'type': 'DRAW', 'requestId': uuid.uuid4().hex, 'expectedRevision': game['revision']}
    after = call('POST', '/v1/games/' + game['gameId'] + '/actions', action, a['playerToken'])
    expect(len(after['hand']) == 8 and after['revision'] == game['revision'] + 1, 'drawing must add a card and one revision')
    expect(after['currentPlayerId'] == b['playerId'], 'drawing ends the turn')
    print('PASS PUBLIC-GAME-DRAW')
    print('Public smoke only; passing does not imply full acceptance. Virtual test data was created.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('task', choices=['GAME'])
    p.add_argument('--url', default='http://127.0.0.1:8080')
    a = p.parse_args()
    try:
        check(a.task, a.url)
    except (Problem, AssertionError, KeyError, TypeError, ValueError) as error:
        print('PUBLIC CHECK NOT PASSED: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
