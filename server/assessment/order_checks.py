import concurrent.futures, uuid, threading
from .check_engine import Unknown, expect

def order_checks(c,check,meta):
    tokens={}
    def login():
        for u in ['customer1','customer2','provider1','provider2']:
            status,body=c.call('POST','/v1/demo-login',{'account':u})
            expect(status==200 and isinstance(body,dict) and isinstance(body.get('token'),str),'登录响应缺少token或状态错误')
            tokens[u]=body['token']
    check('O00','四种演示身份可以登录',login)
    original_check=check
    def check(id,title,fn):
        def guarded():
            if len(tokens)!=4:raise Unknown('前置登录未成功，无法执行此业务用例')
            fn()
        original_check(id,title,guarded, '权限' if id in ('O08','O09','O10') else '一致性' if id in ('O11','O12','O16','O17','O18') else '订单规则')

    def create(u='customer1',**extra):
        s,o=c.call('POST','/v1/orders',{'serviceId':'s1',**extra},tokens[u]);expect(s==200);return o
    def act(o,action,u,key=None,note=''):
        return c.call('POST',f'/v1/orders/{o["id"]}/{action}',{'note':note},tokens[u],key or str(uuid.uuid4()))
    def get(o,u='customer1'):return c.call('GET','/v1/orders/'+o['id'],token=tokens[u])
    def transition(action):
        o=create()
        if action=='complete':expect(act(o,'accept','provider1')[0]==200)
        s,v=act(o,action,'customer1' if action=='cancel' else 'provider1');expect(s==200);expect(v['status']=={'accept':'ACCEPTED','cancel':'CANCELLED','complete':'COMPLETED'}[action]);expect(get(o)[1]==v,'落库后查询与动作结果不同');expect(v['version']==(2 if action=='complete' else 1));expect(v['customerId']==o['customerId'] and v['serviceId']==o['serviceId'] and v['amountFen']==o['amountFen'],'迁移篡改了订单原始字段');expect(v['providerId']==('provider1' if action!='cancel' else None),'接单人不正确')
    for g,a in [('O01','accept'),('O02','cancel'),('O03','complete')]:check(g,'正常'+a,lambda a=a:transition(a))
    def accepted_cancel():
        o=create();expect(act(o,'accept','provider1')[0]==200);before=get(o);expect(act(o,'cancel','customer1')[0]==409);expect(get(o)==before,'非法取消修改了订单')
    check('O04','接单后取消拒绝',accepted_cancel)
    def terminal():
        o=create();expect(act(o,'cancel','customer1')[0]==200);before=get(o);expect(act(o,'accept','provider1')[0]==409);expect(get(o)==before,'取消终态改变');o=create();expect(act(o,'accept','provider1')[0]==200);expect(act(o,'complete','provider1')[0]==200);before=get(o);expect(act(o,'complete','provider1')[0]==409);expect(get(o)==before,'完成终态改变')
    check('O05','取消与完成终态',terminal)
    def invalid():
        o=create();before=get(o);expect(act(o,'complete','provider1')[0]==409);expect(get(o)==before,'待接单时完成改变状态');expect(act(o,'accept','provider1')[0]==200);before=get(o);expect(act(o,'accept','provider1')[0]==409);expect(get(o)==before,'重复接单改变状态')
    check('O06','非法迁移与重复动作',invalid)
    check('O07','不信任客户端价格',lambda:expect(create(amountFen=1)['amountFen']==3000))
    def access():
        o=create();own=create('customer2');expect(get(o,'customer2')[0] in (403,404),'他人详情泄露');s,v=c.call('GET','/v1/orders?page=1&size=100',token=tokens['customer2']);expect(s==200);expect(all(x['customerId']=='customer2' for x in v['items']),'列表泄露他人订单');expect(own['id'] in {x['id'] for x in v['items']},'列表未包含自己的订单')
    check('O08','详情和列表归属',access)
    def roles():
        o=create();before=get(o);expect(act(o,'accept','customer1')[0]==403);expect(act(o,'cancel','provider1')[0]==403);expect(get(o)==before,'越权动作改变了订单')
    check('O09','角色边界',roles)
    def provider():
        o=create();expect(act(o,'accept','provider1')[0]==200);before=get(o);expect(act(o,'complete','provider2')[0]==403);expect(get(o,'provider2')[0] in (403,404));expect(get(o)==before,'越权完成改变了订单')
    check('O10','仅接单人完成与查看',provider)
    def idem():
        o=create();key=str(uuid.uuid4());a=act(o,'accept','provider1',key);b=act(o,'accept','provider1',key);expect(a[0]==200 and a==b,'首次成功响应未被准确重放');expect(act(o,'accept','provider1',key,'different')[0]==409);expect(get(o)[1]['version']==1,'version应只增加一次')
    check('O11','重放与载荷冲突',idem)
    def race(cancel=False):
        for _ in range(10):
            o=create()
            barrier=threading.Barrier(2)
            def synced(action,user):barrier.wait(timeout=5);return act(o,action,user)
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                a=pool.submit(synced,'accept','provider1');b=pool.submit(synced,'cancel' if cancel else 'accept','customer1' if cancel else 'provider2');out=[a.result(),b.result()]
            expect(sorted(x[0] for x in out)==[200,409],'竞争应一次成功一次冲突')
            winner=next(x[1] for x in out if x[0]==200)
            expect(get(o)[1]==winner and winner['version']==1,'持久状态与唯一成功响应不一致')
    check('O12','两人抢单10轮',race);check('O16','接单与取消10轮',lambda:race(True))
    check('O13','不存在订单返回404',lambda:expect(act({'id':'missing'},'accept','provider1')[0]==404))
    def infra_fault():
        if not meta.get('injectDbFailure') or not meta.get('readOrder'):raise Unknown('缺少可信数据库故障控制端或直接读取能力')
        o=create();key=str(uuid.uuid4());control_result=meta['injectDbFailure']();c.record({'source':'trusted-mongodb-failpoint','result':control_result})
        try:act(o,'accept','provider1',key)
        except Unknown:pass
        code,v=act(o,'accept','provider1',key);expect(code==200,'中断后原key无法恢复');expect(v['version']==1)
        if meta.get('readOrder'):
            actual=meta['readOrder'](o['id']);expect(actual['status']=='ACCEPTED' and actual['version']==1,'数据库最终状态错误')
            c.record({'source':'trusted-mongodb','actual':actual})
    check('O17','数据库写入中断一致性',infra_fault)
    check('O14','服务列表与创建查询回归',lambda:expect(c.call('GET','/v1/services')[1][0]['id']=='s1' and get(create())[0]==200))
    def paging():
        created={create()['id'] for _ in range(5)}
        first=c.call('GET','/v1/orders?page=1&size=2',token=tokens['customer1'])[1]
        expect(isinstance(first.get('total'),int) and first['total']>=5,'分页total不正确')
        expect(first['total']<10000,'测试数据超过本用例上限，需要独立数据库')
        ids=[]
        for page in range(1,(first['total']+1)//2+1):
            code,data=c.call('GET',f'/v1/orders?page={page}&size=2',token=tokens['customer1'])
            expect(code==200 and data['total']==first['total'],'分页total不稳定')
            expect(len(data['items'])==min(2,first['total']-(page-1)*2),'分页条数错误')
            expect(all(x['customerId']=='customer1' for x in data['items']),'分页泄露他人订单')
            ids += [x['id'] for x in data['items']]
        expect(len(set(ids))==len(ids)==first['total'] and created<=set(ids),'分页重复、丢失或total错误')
    check('O15','分页无重复',paging)
    def persistence():
        if not meta.get('restart'):raise Unknown('未提供重启控制，不能验证持久化')
        o=create();key=uuid.uuid4().hex;before=act(o,'accept','provider1',key);expect(before[0]==200);c.record({'source':'trusted-process','event':'restart-requested'});meta['restart']();c.record({'source':'trusted-process','event':'restart-completed'});login();expect(get(o)==before,'重启后订单内容改变');expect(act(o,'accept','provider1',key)==before,'重启后幂等回执丢失')
    check('O18','重启后状态保持',persistence)
