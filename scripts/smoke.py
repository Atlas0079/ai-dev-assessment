"""Run trusted references only; passing cases are not candidate quality scores."""
import sys,json,uuid,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from assessment.storage import ROOT,save
from assessment.runner import Reference
from assessment.evaluate import evaluate
parser=argparse.ArgumentParser()
parser.add_argument('--task',choices=['GAME','ORDER'])
parser.add_argument('--output',type=Path)
args=parser.parse_args()
output=args.output or ROOT/'.runtime/checks'/uuid.uuid4().hex[:12]
print('Evidence directory: '+str(output),flush=True)
pending=False
for task in ([args.task] if args.task else ['GAME','ORDER']):
    folder=output/task;folder.mkdir(parents=True,exist_ok=True);service=Reference(task,folder)
    try:
        service.start();result=evaluate(task,service.url,folder,service.meta)
        print(json.dumps({'task':task,'summary':result['summary']},ensure_ascii=False),flush=True)
        for case in result['cases']:
            if case['status']!='PASS':print(json.dumps(case,ensure_ascii=False),flush=True)
        pending |= any(result['summary'][s] for s in ('FAIL','NOT_RUN','ERROR'))
    except Exception as error:
        pending=True;save(folder/'startup-error.json',{'status':'ERROR','detail':str(error)})
        print(json.dumps({'task':task,'evaluated':False,'error':str(error)},ensure_ascii=False),flush=True)
    finally:service.close()
print('WORKFLOW: DEFERRED (documentation only)',flush=True)
sys.exit(2 if pending else 0)
