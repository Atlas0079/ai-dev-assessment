"""Check an already deployed isolated service; do not run uploaded code on HR's machine."""
import argparse,json,os,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from assessment.storage import ROOT
from assessment.evaluate import evaluate
from assessment.report import write_report
from assessment.catalog import QUESTIONS, question

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('task',choices=list(QUESTIONS))
p.add_argument('--url',required=True)
p.add_argument('--control-token-env',default='EVAL_CONTROL_TOKEN')
p.add_argument('--output',type=Path)
p.add_argument('--business-url',help='WORKFLOW evaluator-owned isolated business service')
p.add_argument('--workflow-control-token-env',default='WORKFLOW_CONTROL_TOKEN')
p.add_argument('--candidate-id',default='未指定')
p.add_argument('--model-events',type=Path,help='Fresh evaluator-owned gateway evidence file for this run; never a candidate-supplied log')
a=p.parse_args()
folder=a.output or ROOT/'.runtime/checks'/uuid.uuid4().hex
meta={'mode':'existing-http-service','controlToken':os.environ.get(a.control_token_env),
    'workflowEnabled':question(a.task).pack_profile=='workflow','businessUrl':a.business_url,
    'workflowControlToken':os.environ.get(a.workflow_control_token_env),'modelMode':'unverified'}
if a.model_events:
    if a.model_events.exists():p.error('--model-events must be a new path for a fresh gateway run; old evidence cannot verify this submission')
    def gateway_events():
        if not a.model_events.exists():return []
        value=json.loads(a.model_events.read_text(encoding='utf-8'))
        if value.get('mode')!='real-deepseek':raise ValueError('External model evidence must be real-deepseek')
        return value['calls']
    meta.update(gatewayEvents=gateway_events,modelMode='real-deepseek')
result=evaluate(a.task,a.url,folder,meta)
write_report([result],folder/'面试官报告.md',a.candidate_id,result_sources={a.task:folder})
print(json.dumps({'output':str(folder),'summary':result['summary']},ensure_ascii=False))
sys.exit(2 if any(result['summary'][s] for s in ('FAIL','NOT_RUN','ERROR')) else 0)
