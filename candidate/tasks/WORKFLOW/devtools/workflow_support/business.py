"""Virtual orders, policy and tickets. No production data or payments."""
import argparse
import copy
import json
import secrets
import threading
from .net import Problem, server


class Business:
    def __init__(self):
        self.lock = threading.RLock()
        self.seed()

    def seed(self):
        suffix = secrets.token_hex(3)
        self.tokens = {secrets.token_urlsafe(24): user for user in ('alice', 'bob')}
        self.orders = {
            'ORDER-' + suffix + '-A': {'owner': 'alice', 'status': 'COMPLETED', 'description': '双人游戏陪玩'},
            'ORDER-' + suffix + '-B': {'owner': 'bob', 'status': 'COMPLETED', 'description': '其他用户订单'},
            'ORDER-' + suffix + '-C': {'owner': 'alice', 'status': 'CANCELLED', 'description': '已取消订单'},
        }
        self.policy = {'policy_id': 'POLICY-1', 'allowed_statuses': ['COMPLETED'],
                       'request_types': ['service_incomplete', 'service_quality'],
                       'requires_confirmation': True, 'payment_execution': False}
        self.tickets, self.receipts, self.events = [], {}, []
        return {'tokens': {u: t for t, u in self.tokens.items()},
                'orders': list(self.orders), 'policy': self.policy}

    def __call__(self, method, path, body, token, key):
        with self.lock:
            if path == '/healthz' and method == 'GET':
                return 200, {'status': 'ok'}
            user = self.tokens.get(token)
            if not user:
                raise Problem(401, 'UNAUTHORIZED')
            event = {'method': method, 'path': path, 'user': user, 'body': copy.deepcopy(body)}
            self.events.append(event)
            if path == '/v1/me' and method == 'GET':
                return 200, {'user_id': user}
            if path == '/v1/policy' and method == 'GET':
                return 200, copy.deepcopy(self.policy)
            if path == '/v1/orders' and method == 'GET':
                return 200, {'orders': [dict(order_id=i, **v) for i, v in self.orders.items() if v['owner'] == user]}
            if path.startswith('/v1/orders/') and method == 'GET':
                order = self.orders.get(path.split('/')[-1])
                if not order or order['owner'] != user:
                    event['denied'] = True
                    raise Problem(404, 'ORDER_UNAVAILABLE')
                return 200, dict(order_id=path.split('/')[-1], **order)
            if path == '/v1/tickets' and method == 'GET':
                return 200, {'tickets': [copy.deepcopy(t) for t in self.tickets if t['user_id'] == user]}
            if path == '/v1/tickets' and method == 'POST':
                if not isinstance(key, str) or not key:
                    raise Problem(400, 'IDEMPOTENCY_KEY_REQUIRED')
                previous = self.receipts.get((user, key))
                if previous:
                    if previous['body'] != body:
                        raise Problem(409, 'IDEMPOTENCY_CONFLICT')
                    return 200, copy.deepcopy(previous['ticket'])
                order = self.orders.get(body.get('order_id'))
                if not order or order['owner'] != user:
                    event['denied'] = True
                    raise Problem(403, 'FORBIDDEN')
                if order['status'] not in self.policy['allowed_statuses'] or body.get('request_type') not in self.policy['request_types']:
                    raise Problem(409, 'POLICY_DENIED')
                if not isinstance(body.get('description'), str) or not body['description'].strip():
                    raise Problem(400, 'DESCRIPTION_REQUIRED')
                ticket = dict(body, ticket_id='T-' + secrets.token_hex(6), user_id=user, status='OPEN')
                self.tickets.append(ticket)
                self.receipts[(user, key)] = {'body': copy.deepcopy(body), 'ticket': ticket}
                return 200, copy.deepcopy(ticket)
            raise Problem(404, 'NOT_FOUND')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8091)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    app = Business()
    # Local demo identities are intentionally fictitious; no control token is printed.
    print(json.dumps({'business_url': f'http://127.0.0.1:{args.port}',
                      'demo': {'tokens': {u: t for t, u in app.tokens.items()}, 'orders': list(app.orders)}}, ensure_ascii=False), flush=True)
    server(app, args.port, args.host).serve_forever()
