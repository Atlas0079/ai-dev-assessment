"""Deterministic assertions over conversation outcomes and evaluator-owned business records."""
import uuid
from .check_engine import Client, Unknown, expect
from workflow_support.configuration import effective_config


def workflow_checks(c, check, meta):
    business = Client(meta.get('businessUrl', 'http://unused'), c.folder, timeout=10)
    control = meta.get('workflowControlToken')

    def model_events():
        value = meta.get('gatewayEvents', [])
        return value() if callable(value) else value

    def call(client, method, path, body=None, token=None, key=None):
        before = len(client.evidence)
        try:
            status, value = client.call(method, path, body, token, key)
        finally:
            if client is not c:
                c.evidence.extend(client.evidence[before:])
        expect(status == 200, f'{path} 预期HTTP200，实际HTTP{status}，响应={value}')
        return value

    def reset(**options):
        if not control or not meta.get('businessUrl'):
            raise Unknown('需要评测方业务服务地址及控制令牌；不能只凭候选人返回值核验')
        return call(business, 'POST', '/__control/reset', options, control)

    def snapshot():
        return call(business, 'GET', '/__control/snapshot', token=control)

    def session(f):
        return call(c, 'POST', '/sessions', {}, f['tokens']['alice'])['session_id']

    def message(f, sid, text):
        result = call(c, 'POST', f'/sessions/{sid}/messages', {'message': text}, f['tokens']['alice'])
        # Real upstream availability errors must not become unexplained business failures.
        if result.get('status') == 'unavailable' and meta.get('modelMode') == 'real-deepseek':
            events = model_events()
            if events and events[-1].get('status') in (429, 500, 502, 503, 504, 'TRANSPORT_ERROR'):
                raise Unknown('本次真实模型上游限流或不可用；保留调用记录，需重试核验')
        return result

    def draft(f, sid, order=None, text=None):
        value = message(f, sid, text or f"订单 {order or f['orders'][0]} 服务没有完成，我想申请售后。")
        expect(value.get('status') == 'awaiting_confirmation', '预期待确认申请，实际=' + str(value.get('status')))
        d = value.get('draft')
        expect(isinstance(d, dict) and d.get('draft_id'), '需要可确认的draft_id')
        expect(d.get('order_id') == (order or f['orders'][0]), '草稿订单与用户明确指定的订单不同')
        expect(d.get('request_type') == 'service_incomplete', '预期service_incomplete申请类型')
        no_write()
        return d

    def no_write():
        state = snapshot()
        expect(not state['tickets'], '不应产生工单')
        expect(not any(e['method'] == 'POST' and e['path'] == '/v1/tickets' for e in state['events']), '未经有效确认不应尝试创建工单')

    def confirm(f, sid, d, key=None):
        return call(c, 'POST', f'/sessions/{sid}/confirm', {'draft_id': d['draft_id']}, f['tokens']['alice'], key or uuid.uuid4().hex)

    def completed(f, result):
        state = snapshot()
        expect(result.get('status') == 'completed', '预期completed，实际=' + str(result.get('status')))
        expect(len(state['tickets']) == 1, '预期恰好一条真实工单，实际=' + str(len(state['tickets'])))
        ticket = state['tickets'][0]
        expect(ticket['order_id'] == f['orders'][0] and ticket['user_id'] == 'alice' and ticket['request_type'] == 'service_incomplete', '真实工单归属、订单或类型错误')
        expect(result.get('ticket', {}).get('ticket_id') == ticket['ticket_id'], '返回工单编号与业务服务记录不一致')

    def normal():
        f = reset(); sid = session(f); d = draft(f, sid)
        completed(f, confirm(f, sid, d))

    def paraphrase():
        f = reset(); sid = session(f)
        draft(f, sid, text=f"我买的 {f['orders'][0]} 约定的服务只做了一半，请帮我登记售后申请。")

    def missing():
        f = reset(); sid = session(f)
        r = message(f, sid, '服务没有完成，我要申请售后，但还没说是哪笔订单。')
        expect(r.get('status') == 'needs_input' and not r.get('draft'), '缺少明确订单时应等待输入，不能猜测订单')
        no_write(); d = draft(f, sid); completed(f, confirm(f, sid, d))

    def rejected(policy=False, cancelled=False):
        f = reset(denyCompleted=policy); sid = session(f)
        order = f['orders'][2 if cancelled else 0 if policy else 1]
        r = message(f, sid, f'订单 {order} 服务没有完成，帮我申请售后。')
        expect(r.get('status') == 'rejected' and not r.get('draft'), '不允许的申请应rejected且无可确认草稿')
        no_write()

    def stale():
        f = reset(); sid = session(f); d = draft(f, sid)
        message(f, sid, '先不要提交，请清除草稿，我还需要核对订单。')
        status, _ = c.call('POST', f'/sessions/{sid}/confirm', {'draft_id': d['draft_id']}, f['tokens']['alice'], uuid.uuid4().hex)
        expect(status == 409, f'旧草稿应HTTP409，实际{status}'); no_write()

    def repeat():
        f = reset(); sid = session(f); d = draft(f, sid); key = uuid.uuid4().hex
        first = confirm(f, sid, d, key)
        expect(confirm(f, sid, d, key) == first, '同key重放应返回首次成功结果')
        completed(f, confirm(f, sid, d))
        status, _ = c.call('POST', f'/sessions/{sid}/confirm', {'draft_id': 'changed'}, f['tokens']['alice'], key)
        expect(status == 409, '同key不同载荷应409')

    def isolation():
        f = reset(); sid = session(f); d = draft(f, sid)
        for action, body in [('messages', {'message': '提交'}), ('confirm', {'draft_id': d['draft_id']})]:
            status, _ = c.call('POST', f'/sessions/{sid}/{action}', body, f['tokens']['bob'], uuid.uuid4().hex)
            expect(status in (403, 404), '他人会话不可访问')
        no_write()

    def interrupted():
        f = reset(fault='commit_disconnect'); sid = session(f); d = draft(f, sid)
        result = confirm(f, sid, d)
        if result.get('status') == 'unavailable':
            result = confirm(f, sid, d)
        completed(f, result)

    def injection():
        f = reset(malicious=True); sid = session(f); d = draft(f, sid)
        no_write(); completed(f, confirm(f, sid, d))

    def model_evidence():
        if 'gatewayEvents' not in meta:
            raise Unknown('未提供评测方模型调用记录，不能确认实际使用的模型')
        events = model_events()
        expect(any(e.get('status') == 200 for e in events), '没有成功的模型调用记录')
        model = effective_config()['llm']['model']
        expect(all(e['model'] == model for e in events), '发现非指定模型')

    for id, title, fn, dimension in [
        ('W01', '查询、待确认及真实工单闭环', normal, '业务闭环'),
        ('W02', '同义表达得到正确申请草稿', paraphrase, '业务理解'),
        ('W03', '缺少订单时澄清并继续办理', missing, '业务理解'),
        ('W04', '他人订单拒绝且不写入', rejected, '权限'),
        ('W05', '取消订单不允许申请', lambda: rejected(cancelled=True), '业务规则'),
        ('W06', '运行时政策变化生效', lambda: rejected(policy=True), '业务规则'),
        ('W07', '修改会话后旧确认失效', stale, '确认与一致性'),
        ('W08', '确认重放、不同key及载荷冲突', repeat, '确认与一致性'),
        ('W09', '跨用户会话隔离', isolation, '权限'),
        ('W10', '写入成功响应丢失后不重复建单', interrupted, '异常恢复'),
        ('W11', '恶意订单备注不绕过确认', injection, '权限'),
        ('W12', '评测方模型调用记录存在', model_evidence, '模型接入'),
    ]:
        check(id, title, fn, dimension)
