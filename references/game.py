"""Original UNO reference implementation. No company source is included."""
import copy, os, random, uuid
from common import Problem,serve
rooms={};games={};tokens={}

def control(token):
    if os.environ.get('EVAL_FIXTURES')!='1':raise Problem('NOT_FOUND',404)
    secret=os.environ.get('EVAL_CONTROL_TOKEN')
    if not secret or token!=secret:raise Problem('FORBIDDEN',403)

def validate_fixture(b):
    if not isinstance(b,dict) or set(b)!={'schemaVersion','players','drawPile','discardPile','currentPlayerId','direction','currentColor','revision','status','winnerId'} or b.get('schemaVersion')!='1.0':raise Problem('INVALID_INPUT',400)
    ps=b.get('players'); colors={'R','Y','B','G'}
    if not isinstance(ps,list) or not 2<=len(ps)<=4:raise Problem('INVALID_INPUT',400)
    ids=[];cards=[]
    for p in ps:
        if not isinstance(p,dict) or set(p)!={'id','hand'} or not isinstance(p.get('id'),str) or not p['id'] or not isinstance(p.get('hand'),list) or not p['hand']:raise Problem('INVALID_INPUT',400)
        ids.append(p['id']);cards+=p['hand']
    if len(set(ids))!=len(ids) or b.get('currentPlayerId') not in ids:raise Problem('INVALID_INPUT',400)
    if type(b.get('direction')) is not int or b['direction'] not in (-1,1) or type(b.get('revision')) is not int or b['revision']<0:raise Problem('INVALID_INPUT',400)
    if b.get('status')!='PLAYING' or b.get('winnerId','missing') is not None or b.get('currentColor') not in colors:raise Problem('INVALID_INPUT',400)
    if not isinstance(b.get('drawPile'),list) or not isinstance(b.get('discardPile'),list) or not b['discardPile']:raise Problem('INVALID_INPUT',400)
    cards+=b['drawPile']+b['discardPile'];seen=set()
    for card in cards:
        if not isinstance(card,dict) or set(card)!={'cardId','color','value'}:raise Problem('INVALID_INPUT',400)
        cid=card['cardId'];color=card['color'];value=card['value']
        if not isinstance(cid,str) or not cid or cid in seen:raise Problem('INVALID_INPUT',400)
        if not isinstance(color,str) or not isinstance(value,str):raise Problem('INVALID_INPUT',400)
        if not ((color in colors and value in [str(i) for i in range(10)]+['SKIP','REVERSE','DRAW2']) or (color=='W' and value=='WILD')):raise Problem('INVALID_INPUT',400)
        seen.add(cid)
    top=b['discardPile'][-1]
    if top['color']!='W' and top['color']!=b['currentColor']:raise Problem('INVALID_INPUT',400)

def full_state(g):
    return {'schemaVersion':'1.0', **{k:copy.deepcopy(g[k]) for k in ('gameId','drawPile','discardPile','currentPlayerId','direction','currentColor','revision','status','winnerId')},
            'players':[{'id':p,'hand':copy.deepcopy(g['hands'][p])} for p in g['players']]}
def uid():return uuid.uuid4().hex[:12]
def user(token):
    if token not in tokens:raise Problem('UNAUTHENTICATED',401)
    return tokens[token]
def state(g,p):
    return {k:copy.deepcopy(v) for k,v in g.items() if k in ('gameId','currentPlayerId','direction','currentColor','revision','winnerId','status')}|{'hand':copy.deepcopy(g['hands'][p]),'players':[{'playerId':x,'count':len(g['hands'][x])} for x in g['players']],'top':copy.deepcopy(g['discardPile'][-1]),'drawCount':len(g['drawPile'])}
def draw(g,p,n):
    for _ in range(n):
        if not g['drawPile'] and len(g['discardPile'])>1:
            g['drawPile']=g['discardPile'][:-1];g['discardPile']=g['discardPile'][-1:];random.Random(g['revision']).shuffle(g['drawPile'])
        if g['drawPile']:g['hands'][p].append(g['drawPile'].pop(0))
def following(g,p,steps=1):return g['players'][(g['players'].index(p)+g['direction']*steps)%len(g['players'])]
def app(method,path,b,token,q):
    if path=='/__test/fixtures' and method=='POST':
        control(token);validate_fixture(b);b=copy.deepcopy(b)
        gid=uid(); players=[p['id'] for p in b['players']]
        g={'gameId':gid,'players':players,'hands':{p['id']:p['hand'] for p in b['players']},'drawPile':b.get('drawPile',[]),'discardPile':b['discardPile'],'currentPlayerId':b.get('currentPlayerId',players[0]),'direction':b.get('direction',1),'currentColor':b.get('currentColor',b['discardPile'][-1]['color']),'revision':b.get('revision',0),'winnerId':None,'status':'PLAYING','requests':{}}
        games[gid]=g;ts={}
        for p in players:ts[p]=uid();tokens[ts[p]]=(p,gid)
        return 200,{'gameId':gid,'tokens':ts}
    if path.startswith('/__test/games/') and method=='GET':
        control(token);g=games.get(path.split('/')[-1])
        if not g:raise Problem('NOT_FOUND',404)
        return 200,full_state(g)
    if path=='/v1/rooms' and method=='POST':
        p=uid();t=uid();r=uid();tokens[t]=(p,r);rooms[r]={'players':[p],'ready':{},'host':p,'gameId':None,'requests':{}}
        return 200,{'roomId':r,'playerId':p,'playerToken':t}
    parts=path.strip('/').split('/')
    if len(parts)>=3 and parts[:2]==['v1','rooms']:
        r=rooms.get(parts[2]);
        if not r:raise Problem('NOT_FOUND',404)
        op=parts[3] if len(parts)>3 else ''
        if op=='join' and method=='POST':
            if r['gameId'] or len(r['players'])>=4:raise Problem('ROOM_FULL_OR_STARTED')
            p=uid();t=uid();tokens[t]=(p,parts[2]);r['players'].append(p);return 200,{'roomId':parts[2],'playerId':p,'playerToken':t}
        p,scope=user(token)
        if p not in r['players'] or scope!=parts[2]:raise Problem('FORBIDDEN',403)
        if method=='GET':return 200,{'players':r['players'],'ready':r['ready'],'gameId':r['gameId'],'host':r['host']}
        if method!='POST' or op not in ('ready','start'):raise Problem('NOT_FOUND',404)
        if not isinstance(b.get('requestId'),str) or not b['requestId']:raise Problem('INVALID_INPUT',400)
        key=p+':'+op+':'+b['requestId']
        if key in r['requests']:
            old,res=r['requests'][key]
            if old!=b:raise Problem('IDEMPOTENCY_CONFLICT')
            return 200,copy.deepcopy(res)
        if op=='ready':
            if r['gameId']:raise Problem('GAME_STARTED')
            if type(b.get('ready')) is not bool:raise Problem('INVALID_INPUT',400)
            r['ready'][p]=b['ready'];res={'ready':copy.deepcopy(r['ready'])};r['requests'][key]=(copy.deepcopy(b),res)
            return 200,res
        if op=='start':
            if p!=r['host']:raise Problem('FORBIDDEN',403)
            if r['gameId'] or len(r['players'])<2 or not all(r['ready'].get(x) for x in r['players']):raise Problem('NOT_READY')
            deck=[{'cardId':f'{c}-{v}','color':c,'value':str(v)} for c in ['R','Y','B','G'] for v in list(range(10))+['SKIP','REVERSE','DRAW2']]+[{'cardId':f'W-{i}','color':'W','value':'WILD'} for i in range(8)]
            random.shuffle(deck);hands={x:[deck.pop(0) for _ in range(7)] for x in r['players']}
            while not deck[0]['value'].isdigit():deck.append(deck.pop(0))
            top=deck.pop(0);gid=uid();g={'gameId':gid,'players':r['players'][:],'hands':hands,'drawPile':deck,'discardPile':[top],'currentPlayerId':p,'direction':1,'currentColor':top['color'],'revision':0,'winnerId':None,'status':'PLAYING','requests':{}};games[gid]=g;r['gameId']=gid
            g['roomId']=parts[2];res=state(g,p);r['requests'][key]=(copy.deepcopy(b),copy.deepcopy(res));return 200,res
    if len(parts)>=3 and parts[:2]==['v1','games']:
        p,scope=user(token);g=games.get(parts[2])
        if not g:raise Problem('NOT_FOUND',404)
        if p not in g['players'] or scope not in (g['gameId'],g.get('roomId')):raise Problem('FORBIDDEN',403)
        if method=='GET':return 200,state(g,p)
        if method!='POST' or len(parts)!=4 or parts[3]!='actions':raise Problem('NOT_FOUND',404)
        if not isinstance(b.get('requestId'),str) or not b['requestId'] or type(b.get('expectedRevision')) is not int or b['expectedRevision']<0:raise Problem('INVALID_INPUT',400)
        req=b['requestId'];key=p+':'+req
        if key in g['requests']:
            old,res=g['requests'][key]
            if old!=b:raise Problem('IDEMPOTENCY_CONFLICT')
            if os.environ.get('BROKEN')!='1':return 200,res
        if g['status']!='PLAYING':raise Problem('GAME_ENDED')
        if g['currentPlayerId']!=p:raise Problem('NOT_YOUR_TURN',403)
        if b['expectedRevision']!=g['revision']:raise Problem('STALE_REVISION')
        nextp=following(g,p)
        if b['type']=='DRAW':draw(g,p,1)
        elif b['type']=='PLAY':
            card=next((c for c in g['hands'][p] if c['cardId']==b['cardId']),None)
            if not card:raise Problem('INVALID_CARD')
            if card['value']=='WILD':
                if b.get('chosenColor') not in ['R','Y','B','G']:raise Problem('INVALID_COLOR',400)
            elif card['color']!=g['currentColor'] and card['value']!=g['discardPile'][-1]['value']:raise Problem('INVALID_PLAY')
            g['hands'][p].remove(card);g['discardPile'].append(card);g['currentColor']=b['chosenColor'] if card['value']=='WILD' else card['color']
            if card['value']=='SKIP':nextp=following(g,p,2)
            if card['value']=='REVERSE':g['direction']*=-1;nextp=p if len(g['players'])==2 else following(g,p)
            if card['value']=='DRAW2':draw(g,nextp,2);nextp=following(g,p,2)
            if not g['hands'][p]:g['winnerId']=p;g['status']='FINISHED'
        else:raise Problem('INVALID_ACTION',400)
        g['currentPlayerId']=nextp;g['revision']+=1;res=state(g,p);g['requests'][key]=(copy.deepcopy(b),copy.deepcopy(res));return 200,res
    raise Problem('NOT_FOUND',404)
if __name__=='__main__':serve(app,'GAME')
