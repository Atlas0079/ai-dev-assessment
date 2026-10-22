"""Executable observations; no scores, recommendations, or workflow grading."""
from .check_engine import Client, Suite, Unknown, expect
from .storage import save
from .catalog import question
from datetime import datetime, timezone

RESULT_SCHEMA_VERSION = '1.0'


def subjective_placeholder():
    return {'status': 'NOT_ENABLED', 'source': None, 'suggestions': []}


def unexecuted_result(task):
    spec = question(task)
    return {'resultSchemaVersion': RESULT_SCHEMA_VERSION, 'evaluationType': 'objective',
            'task': task, 'businessLine': spec.business_line, 'checkVersion': spec.check_version,
            'status': 'NOT_RUN', 'evaluatedAt': None, 'execution': {}, 'cases': [],
            'summary': {s: 0 for s in ('PASS', 'FAIL', 'NOT_RUN', 'ERROR')}, 'dimensions': {},
            'notAssessed': ['已提交，但没有提供该题测试结果'], 'subjective': subjective_placeholder()}


def evaluate(task,url,folder,metadata=None):
    metadata=metadata or {};folder.mkdir(parents=True,exist_ok=True)
    spec=question(task)
    c=Client(url,folder/'evidence',timeout=spec.timeout);suite=Suite(c,folder)
    def health():
        status,body=c.call('GET','/healthz')
        expect(status==200 and isinstance(body,dict) and body.get('status')=='ok','健康接口需要200和status=ok，允许附加运行信息')
    suite.check('HEALTH','GET /healthz 返回200和status=ok',health,'运行接口')
    spec.checker(c,suite.check,metadata)
    result={'resultSchemaVersion':RESULT_SCHEMA_VERSION,'evaluationType':'objective',
            'businessLine':spec.business_line,'subjective':subjective_placeholder(),
            'checkVersion':spec.check_version,'task':task,'status':'CHECKED',
            'summary':suite.summary(),'cases':suite.cases,
            'notAssessed':['AI使用过程和开发速度','容器构建可复现性',*spec.not_assessed],
            'execution':{k:metadata[k] for k in ('mode','storage','environmentVersion','workflowServicesVersion') if k in metadata}}
    if spec.pack_profile=='workflow':
        result['execution']['modelMode']=metadata.get('modelMode','unverified')
        if metadata.get('modelMode')!='real-deepseek':
            from workflow_support.configuration import effective_config
            model=effective_config()['llm']['model']
            result['notAssessed'].append('真实'+model+'能力：本次未验证真实模型调用')
    result['dimensions']={d:{s:sum(x['dimension']==d and x['status']==s for x in suite.cases) for s in ('PASS','FAIL','NOT_RUN','ERROR')} for d in sorted({x['dimension'] for x in suite.cases})}
    result['evaluatedAt']=datetime.now(timezone.utc).isoformat()
    save(folder/'result.json',result);return result
