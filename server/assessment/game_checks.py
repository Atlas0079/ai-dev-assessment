"""HTTP checks with independently constructed expected state, not reference internals."""
import copy
import uuid
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from .check_engine import Unknown, expect


def card(id, color='R', value='1'):
    return dict(cardId=id, color=color, value=value)


def fixture_body(value='1', color='R', n=3, last=False):
    return dict(schemaVersion='1.0', players=[dict(id='A', hand=[card('play',color,value)]+([] if last else [card('extra','B','9')]))]+
                [dict(id=p,hand=[card(p,'G','4')]) for p in ['B','C','D'][:n-1]],
                drawPile=[card('d1','Y','2'),card('d2','B','3')],discardPile=[card('top')],
                currentPlayerId='A',direction=1,currentColor='R',revision=0,status='PLAYING',winnerId=None)


def game_checks(c, check, meta):
    control=meta.get('controlToken')
    def protected_check(id,title,fn,dimension='游戏规则'):
        def guarded():
            if not control:raise Unknown('未配置测试控制令牌，未执行牌局检查')
            fn()
        check(id,title,guarded,dimension)
    def ok(response):
        status,body=response
        expect(status==200 and isinstance(body,dict),f'预期200和JSON对象，实际HTTP {status}')
        return body
    def fixture(body=None):
        f=ok(c.call('POST','/__test/fixtures',body or fixture_body(),control))
        expect(isinstance(f.get('gameId'),str) and isinstance(f.get('tokens'),dict),'fixture响应需要gameId和tokens')
        return f
    def full(f):return ok(c.call('GET','/__test/games/'+f['gameId'],token=control))
    def state(f,p='A'):return ok(c.call('GET','/v1/games/'+f['gameId'],token=f['tokens'][p]))
    def move(f,p='A',**args):
        return c.call('POST','/v1/games/'+f['gameId']+'/actions',dict(type='PLAY',requestId=uuid.uuid4().hex,expectedRevision=0,cardId='play',**{})|args,f['tokens'][p])
    def equal(actual,expected,why):expect(actual==expected,why+'；完整输入输出见证据')
    def snapshot(f,body):
        actual=full(f);equal(actual,dict(body,gameId=f['gameId']),'完整牌局与预期不一致');return actual
    def unchanged(f,before):equal(full(f),before,'被拒绝的请求改变了牌局')
    def bag(body):
        cards=body['drawPile']+body['discardPile']+sum((p['hand'] for p in body['players']),[])
        return Counter((x['cardId'],x['color'],x['value']) for x in cards)

    def contract():
        b=fixture_body();f=fixture(b);snapshot(f,b)
        for p in b['players']:
            equal(state(f,p['id'])['hand'],p['hand'],'玩家接口与fixture手牌不一致')
    protected_check('G01','测试牌局注入及完整状态往返一致',contract,'数据契约')
    def auth():
        expect(c.call('POST','/__test/fixtures',fixture_body())[0] in (401,403),'未授权用户可注入牌局')
        f=fixture()
        for token in (None,'invalid',f['tokens']['A']):
            expect(c.call('GET','/__test/games/'+f['gameId'],token=token)[0] in (401,403),'完整牌局控制权限泄露')
            expect(c.call('POST','/__test/fixtures',fixture_body(),token)[0] in (401,403),'普通令牌可注入牌局')
    protected_check('G02','测试控制接口拒绝未授权及普通玩家',auth,'权限')
    def malformed():
        invalid=[]
        for field,val in [('schemaVersion','x'),('direction',0),('revision',True),('currentPlayerId','missing'),('drawPile',None),('discardPile',[]),('currentColor','Y')]:
            b=fixture_body();b[field]=val;invalid.append(b)
        b=fixture_body();b['players'][1]['id']='A';invalid.append(b)
        b=fixture_body();b['players'][1]['hand'][0]['cardId']='play';invalid.append(b)
        b=fixture_body();b['players'][0]['hand'][0]['value']='WILD';invalid.append(b)
        for b in invalid:expect(c.call('POST','/__test/fixtures',b,control)[0]==400,'非法牌局未被400拒绝')
    protected_check('G03','10种非法牌局结构被拒绝',malformed,'数据契约')

    def room(n):
        a=ok(c.call('POST','/v1/rooms',{'displayName':'A'}));members=[a];path='/v1/rooms/'+a['roomId']
        for i in range(n-1):members.append(ok(c.call('POST',path+'/join',{'displayName':str(i)})))
        return path,members
    def ready(path,p):return ok(c.call('POST',path+'/ready',{'ready':True,'requestId':uuid.uuid4().hex},p['playerToken']))
    def start(path,p,req=None):return c.call('POST',path+'/start',{'requestId':req or uuid.uuid4().hex},p['playerToken'])
    def initial(n):
        path,ps=room(n)
        for p in ps:ready(path,p)
        g=ok(start(path,ps[0]));b=full(g)
        expect([x['id'] for x in b['players']]==[x['playerId'] for x in ps],'座位顺序改变')
        expect(all(len(p['hand'])==7 for p in b['players']),'初始手牌不是每人7张')
        allcards=list(bag(b).elements());expect(len(allcards)==60 and len({x[0] for x in allcards})==60,'60张牌不完整或cardId重复')
        expected=Counter((color,str(v)) for color in 'RYBG' for v in list(range(10))+['SKIP','REVERSE','DRAW2'])
        expected[('W','WILD')]=8
        equal(Counter((x[1],x[2]) for x in allcards),expected,'牌型组成错误')
        expect(len(b['discardPile'])==1 and b['discardPile'][0]['value'].isdigit(),'首张弃牌应为数字牌')
        expect(len(b['drawPile'])==59-7*n,'初始牌库数量错误')
        expect(b['revision']==0 and b['status']=='PLAYING' and b['winnerId'] is None and b['direction']==1 and b['currentPlayerId']==ps[0]['playerId'],'开局状态错误')
        for p in ps:
            public=ok(c.call('GET','/v1/games/'+g['gameId'],token=p['playerToken']))
            equal(public['hand'],next(x['hand'] for x in b['players'] if x['id']==p['playerId']),'发牌未映射到玩家接口')
    for n in (2,4):protected_check('G04' if n==2 else 'G05',f'{n}人正常开局：60张牌组成、唯一性及每人7张',lambda n=n:initial(n),'开局')
    def room_rules():
        path,ps=room(1);ready(path,ps[0]);expect(start(path,ps[0])[0]==409,'单人允许开局')
        path,ps=room(2);ready(path,ps[0]);expect(start(path,ps[0])[0]==409,'未全部准备可开局')
        ready(path,ps[1]);expect(start(path,ps[1])[0]==403,'非房主可开局')
        expect(start(path,ps[0])[0]==200,'房主无法开局')
        expect(start(path,ps[0])[0]==409,'同一房间重复创建对局')
        expect(c.call('POST',path+'/join',{'displayName':'late'})[0]==409,'开局后仍可加入')
        path,ps=room(4);expect(c.call('POST',path+'/join',{'displayName':'fifth'})[0]==409,'房间超过4人')
    protected_check('G06','人数、准备、房主、重复开局及加入限制',room_rules,'开局')
    def room_idem():
        path,ps=room(2);body={'ready':True,'requestId':'ready-1'}
        a=c.call('POST',path+'/ready',body,ps[0]['playerToken']);ready(path,ps[1])
        equal(c.call('POST',path+'/ready',body,ps[0]['playerToken']),a,'准备重放未返回首次结果')
        expect(c.call('POST',path+'/ready',dict(body,ready=False),ps[0]['playerToken'])[0]==409,'准备载荷冲突未拒绝')
        a=start(path,ps[0],'start-1');expect(a[0]==200,'开局失败');equal(start(path,ps[0],'start-1'),a,'开局重放未返回首次结果')
    protected_check('G07','准备和开局请求幂等',room_idem,'一致性')

    def play(value='1',color='R',n=3,last=False,chosen=None,direction=1):
        b=fixture_body(value,color,n,last);b['direction']=direction;f=fixture(b);snapshot(f,b)
        args={} if chosen is None else {'chosenColor':chosen}
        response=ok(move(f,**args));expected=copy.deepcopy(b)
        played=expected['players'][0]['hand'].pop(0);expected['discardPile'].append(played)
        expected['currentColor']=chosen if value=='WILD' else color
        expected['revision']=1
        delta=direction
        if value=='SKIP':delta=2*direction
        if value=='REVERSE':expected['direction']=-direction;delta=0 if n==2 else -direction
        if value=='DRAW2':
            victim=expected['players'][direction % n]
            victim['hand']+=expected['drawPile'][:2];expected['drawPile']=expected['drawPile'][2:];delta=2*direction
        expected['currentPlayerId']=expected['players'][delta % n]['id']
        if last:expected['status']='FINISHED';expected['winnerId']='A'
        after=snapshot(f,expected);equal(bag(after),bag(b),'出牌改变了牌的总集合')
        equal(response,state(f),'动作响应与最新公开状态不同')
        return f,after
    for id,title,args in [
        ('G08','同色出牌：移牌、轮转、revision及守恒',{}),
        ('G09','同值异色出牌',{'color':'G'}),
        ('G10','SKIP跳过一人',{'value':'SKIP'}),
        ('G11','三人REVERSE改变方向',{'value':'REVERSE'}),
        ('G12','两人REVERSE回到自己',{'value':'REVERSE','n':2}),
        ('G13','DRAW2实际补两张且跳过受罚者',{'value':'DRAW2'}),
        ('G14','两人DRAW2回到自己',{'value':'DRAW2','n':2}),
        ('G15','WILD指定颜色',{'value':'WILD','color':'W','chosen':'B'}),
        ('G16','逆时针出牌轮转',{'direction':-1}),
        ('G17','最后一张数字牌产生胜者',{'last':True}),
        ('G18','最后一张DRAW2先处罚再结束',{'value':'DRAW2','last':True})]:
        protected_check(id,title,lambda args=args:play(**args))
    def draw_case(recycle=False,empty=False):
        b=fixture_body()
        if recycle or empty:b['drawPile']=[]
        if recycle:b['discardPile']=[card('old','Y','8')]+b['discardPile']
        f=fixture(b);ok(move(f,type='DRAW'));expected=copy.deepcopy(b)
        if recycle:expected['players'][0]['hand'].append(expected['discardPile'].pop(0))
        elif not empty:expected['players'][0]['hand'].append(expected['drawPile'].pop(0))
        expected['currentPlayerId']='B';expected['revision']=1
        after=snapshot(f,expected);equal(bag(after),bag(b),'摸牌改变了牌集合')
    protected_check('G19','摸牌：确实增加一张、牌库减少、结束回合',draw_case)
    protected_check('G20','耗尽牌库回收弃牌且保留顶牌',lambda:draw_case(recycle=True))
    protected_check('G21','无可回收牌时摸牌仍结束回合',lambda:draw_case(empty=True))
    def invalid(value='1',color='R',p='A',status=409,**args):
        f=fixture(fixture_body(value,color));before=full(f)
        expect(move(f,p,**args)[0]==status,f'非法动作应返回{status}');unchanged(f,before)
    for id,title,opts in [
        ('G22','不匹配牌拒绝且状态不变',dict(value='5',color='G')),
        ('G23','不持有的牌拒绝且状态不变',dict(cardId='missing')),
        ('G24','非当前玩家拒绝且状态不变',dict(p='B',status=403)),
        ('G25','旧revision拒绝且状态不变',dict(expectedRevision=9)),
        ('G26','WILD缺少颜色拒绝且状态不变',dict(value='WILD',color='W',status=400)),
        ('G27','未知动作拒绝且状态不变',dict(type='INVALID',status=400))]:
        protected_check(id,title,lambda opts=opts:invalid(**opts),'拒绝与边界')
    def terminal():
        f,before=play(last=True)
        for p in ('A','B'):
            for type in ('PLAY','DRAW'):
                expect(move(f,p,type=type,expectedRevision=1)[0]==409,'终态仍接受新动作');unchanged(f,before)
    protected_check('G28','结束后出牌和摸牌均拒绝且状态不变',terminal,'拒绝与边界')
    def privacy():
        b=fixture_body();f=fixture(b)
        for player in b['players']:
            public=state(f,player['id']);own=player['hand']
            equal(set(public),{'gameId','currentPlayerId','direction','currentColor','revision','winnerId','status','hand','players','top','drawCount'},'公开响应字段不符合白名单')
            equal(public['hand'],own,'本人的手牌错误')
            equal(public['players'],[{'playerId':p['id'],'count':len(p['hand'])} for p in b['players']],'其他玩家只可显示张数')
            equal(public['top'],b['discardPile'][-1],'弃牌顶牌错误')
            hidden={x['cardId'] for p in b['players'] if p['id']!=player['id'] for x in p['hand']}|{x['cardId'] for x in b['drawPile']}
            def card_ids(v):
                if isinstance(v,dict):return ({v['cardId']} if 'cardId' in v else set())|set().union(*(card_ids(x) for x in v.values()))
                if isinstance(v,list):return set().union(*(card_ids(x) for x in v))
                return set()
            expect(not(hidden & card_ids(public)),'公开响应泄露未知牌')
    protected_check('G29','公开状态严格字段契约及手牌隔离',privacy,'权限')
    def player_auth():
        f=fixture();other=fixture();before=full(f)
        for token,code in [('fake',401),(other['tokens']['A'],403)]:
            expect(c.call('GET','/v1/games/'+f['gameId'],token=token)[0]==code,'越权读取未拒绝')
            expect(c.call('POST','/v1/games/'+f['gameId']+'/actions',{'type':'DRAW','requestId':'x','expectedRevision':0},token)[0]==code,'越权动作未拒绝')
            unchanged(f,before)
    protected_check('G30','伪造令牌及跨局同名玩家隔离',player_auth,'权限')
    def idem():
        f=fixture();a=move(f,requestId='same');expect(a[0]==200,'首次出牌失败');before=full(f)
        equal(move(f,requestId='same'),a,'成功动作未准确重放');unchanged(f,before)
        expect(move(f,requestId='same',cardId='extra')[0]==409,'相同requestId不同载荷未拒绝');unchanged(f,before)
    protected_check('G31','动作重放与冲突均不重复变更状态',idem,'一致性')
    def race():
        for _ in range(10):
            b=fixture_body();f=fixture(b);barrier=threading.Barrier(2)
            def action():barrier.wait(timeout=5);return move(f,type='DRAW')
            with ThreadPoolExecutor(2) as pool:
                fs=[pool.submit(action) for i in range(2)];responses=[f.result() for f in fs]
            expect(sum(r[0]==200 for r in responses)==1 and all(r[0] in (200,403,409) for r in responses),'同revision竞争应只有一次成功，另一次拒绝')
            expected=copy.deepcopy(b);expected['players'][0]['hand'].append(expected['drawPile'].pop(0));expected['revision']=1;expected['currentPlayerId']='B';snapshot(f,expected)
    protected_check('G32','10轮并发动作仅一次生效并验证实际手牌',race,'一致性')
