"""Verify checks against intentionally damaged copies of trusted reference code."""
import json,os,shutil,subprocess,sys,uuid,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from assessment.storage import ROOT,save
from assessment.runner import Reference,free_port,wait_health
from assessment.evaluate import evaluate

p=argparse.ArgumentParser();p.add_argument('--output',type=Path);a=p.parse_args()
root=a.output or ROOT/'.runtime/checks'/('defects-'+uuid.uuid4().hex[:8]);root.mkdir(parents=True,exist_ok=True)
source=(ROOT/'references/game.py').read_text(encoding='utf-8')
mutations=[
 ('draw-does-not-add-card',"if b['type']=='DRAW':draw(g,p,1)","if b['type']=='DRAW':pass",'G19'),
 ('private-hand-leak',"'drawCount':len(g['drawPile'])}","'drawCount':len(g['drawPile']),'debug':{'hands':copy.deepcopy(g['hands'])}}",'G29'),
 ('no-idempotent-replay',"if os.environ.get('BROKEN')!='1':return 200,res","if False:return 200,res",'G31'),
 ('skip-does-not-skip',"if card['value']=='SKIP':nextp=following(g,p,2)","if card['value']=='SKIP':nextp=following(g,p,1)",'G10')]
results=[]
for name,old,new,target in mutations:
    folder=root/name;folder.mkdir();expect_count=source.count(old)
    if expect_count!=1:raise RuntimeError(f'{name}: mutation target count={expect_count}')
    (folder/'game.py').write_text(source.replace(old,new),encoding='utf-8');shutil.copyfile(ROOT/'references/common.py',folder/'common.py')
    port=free_port();token=uuid.uuid4().hex;env=os.environ.copy();env.update(PORT=str(port),EVAL_FIXTURES='1',EVAL_CONTROL_TOKEN=token,BROKEN='0')
    with (folder/'application.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,str((folder/'game.py').resolve())],env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            url=f'http://127.0.0.1:{port}';wait_health(url,process)
            report=evaluate('GAME',url,folder,{'controlToken':token,'mode':'intentional-defect'})
            case=next(x for x in report['cases'] if x['id']==target)
            results.append({'defect':name,'expectedDetection':target,'actualStatus':case['status'],'detected':case['status']=='FAIL'})
        finally:process.terminate();process.wait(timeout=10)
folder=root/'order-detail-access';service=Reference('ORDER',folder,broken=True)
try:
    service.start();report=evaluate('ORDER',service.url,folder,service.meta)
    case=next(x for x in report['cases'] if x['id']=='O08')
    results.append({'defect':'order-detail-access','expectedDetection':'O08','actualStatus':case['status'],'detected':case['status']=='FAIL'})
finally:service.close()
save(root/'defect-verification.json',results)
print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)
sys.exit(0 if all(r['detected'] for r in results) else 2)
