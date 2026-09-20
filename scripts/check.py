"""Check an already deployed isolated service; do not run uploaded code on HR's machine."""
import argparse,json,os,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from assessment.storage import ROOT
from assessment.evaluate import evaluate

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('task',choices=['GAME','ORDER'])
p.add_argument('--url',required=True)
p.add_argument('--control-token-env',default='EVAL_CONTROL_TOKEN')
p.add_argument('--output',type=Path)
a=p.parse_args()
folder=a.output or ROOT/'.runtime/checks'/uuid.uuid4().hex
result=evaluate(a.task,a.url,folder,{'mode':'existing-http-service','controlToken':os.environ.get(a.control_token_env)})
print(json.dumps({'output':str(folder),'summary':result['summary']},ensure_ascii=False))
sys.exit(2 if any(result['summary'][s] for s in ('FAIL','NOT_RUN','ERROR')) else 0)
