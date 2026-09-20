"""Executable observations; no scores, recommendations, or workflow grading."""
from .check_engine import Client, Suite, Unknown, expect
from .storage import save
from .game_checks import game_checks
from .order_checks import order_checks

def evaluate(task,url,folder,metadata=None):
    metadata=metadata or {};folder.mkdir(parents=True,exist_ok=True)
    if task not in ('GAME','ORDER','WORKFLOW'):raise ValueError('Unknown task')
    c=Client(url,folder/'evidence');suite=Suite(c,folder)
    if task!='WORKFLOW':
        def health():
            status,body=c.call('GET','/healthz')
            expect(status==200 and isinstance(body,dict) and body.get('status')=='ok','健康接口需要200和status=ok，允许附加运行信息')
        suite.check('HEALTH','GET /healthz 返回200和status=ok',health,'运行接口')
        (game_checks if task=='GAME' else order_checks)(c,suite.check,metadata)
    result={'checkVersion':'2.0','task':task,'status':'DEFERRED' if task=='WORKFLOW' else 'CHECKED',
            'summary':suite.summary(),'cases':suite.cases,
            'notAssessed':['综合分数与录用建议','AI使用能力和开发速度','代码质量与可维护性','页面操作、刷新同步和体验','容器构建可复现性'],
            'execution':{k:metadata[k] for k in ('mode','storage') if k in metadata}}
    if task=='WORKFLOW':result['notAssessed']=['AI工作流全部执行与评分；仅保留设计草案']
    result['dimensions']={d:{s:sum(x['dimension']==d and x['status']==s for x in suite.cases) for s in ('PASS','FAIL','NOT_RUN','ERROR')} for d in sorted({x['dimension'] for x in suite.cases})}
    save(folder/'result.json',result);return result
