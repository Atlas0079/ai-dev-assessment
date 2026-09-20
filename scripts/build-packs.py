"""Generate question packs from current contracts; no answers or numerical grading."""
import json,zipfile,re,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];dist=root/'dist';dist.mkdir(exist_ok=True)
common="""# 候选人实操说明 2.0

48小时窗口，当前可以选择GAME（UNO）或ORDER（Java订单）作为主任务，也可两题都做。WORKFLOW仅为设计草案，本期不作答。额外题目不自动加分，不把可支配时间等同于重视程度。
允许使用熟悉的AI工具。说明模板/依赖来源，不提交公司保密源码、真实个人数据或私人API密钥。费用与截止时间由发题联系人确认。
本版自动检查只输出具体用例的证据和状态，不提供总分、排名或录用结论。代码质量、页面体验、AI使用能力需要后续人工了解。

提交ZIP文件名固定为 <候选人编号>_v<提交版本>.zip，例如 C20260001_v1.zip；候选人编号由HR发放，不使用姓名作文件名。版本为正整数，修改后递增。当前由HR人工检查名称和接收，没有网页上传系统。
ZIP根目录直接放submission.json和所选工程目录GAME/ORDER。每个工程含源码、Dockerfile、README.md。README写启动配置、已完成范围、自测步骤与已知问题。
示例submission.json：{"schemaVersion":"2.0","candidateId":"C20260001","submissionVersion":1,"primaryTask":"GAME","tasks":["GAME"]}。
不要套额外一层目录，不包含node_modules、target、.git、依赖缓存或个人密钥。不把整份考试题包当作交付。
服务监听0.0.0.0:8080，GET /healthz返回HTTP200及status=ok。计划容器环境为Linux amd64、2CPU/4GB；当前Docker链路尚未实机验证，正式发题前由招聘方校验部署条件。
在线地址和录像可补充说明，但不能替代可重跑源码。人工收发、截止时间和补交安排由HR负责。
"""
docker='FROM python:3.13-slim\nWORKDIR /app\nCOPY . /app\nUSER 10001\nCMD ["python","app.py"]\n'
skeleton="""from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,os
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path=='/healthz' else 501)
        self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps({'status':'ok'} if self.path=='/healthz' else {'code':'NOT_IMPLEMENTED'}).encode())
    def do_POST(self):
        self.send_response(501);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"code":"NOT_IMPLEMENTED"}')
ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler).serve_forever()
"""
for task in ('GAME','ORDER'):
    files={'开始前请读.md':common}
    for doc in (root/'questions'/task).rglob('*'):
        if doc.is_file():files[doc.relative_to(root/'questions'/task).as_posix()]=doc.read_text(encoding='utf-8')
    if task=='GAME':
        files['GAME/app.py']=skeleton;files['GAME/Dockerfile']=docker
        files['GAME/README.md']='# GAME开发起点\n这里只提供健康接口；游戏、页面、测试接口均需自行实现。运行 python app.py，默认8080端口。测试配置和数据结构见题目契约。\n'
    else:
        for p in (root/'order-reference').rglob('*'):
            if not p.is_file() or any(x in ('target','.git') for x in p.parts):continue
            relative=p.relative_to(root/'order-reference').as_posix()
            if 'MemoryOrderDao' in relative or 'application-demo' in relative:continue
            text=p.read_text(encoding='utf-8')
            if relative.endswith('OrderService.java'):
                text='''package assessment.service;
import assessment.api.*;import assessment.dao.OrderDao;import assessment.support.Problem;
import org.springframework.stereotype.Service;import java.util.Map;
@Service public class OrderService implements OrderOperations {
 private final OrderDao dao;public OrderService(OrderDao d){dao=d;}
 public Map<String,Object> transition(String id,String user,String action,String key,String note){
  // TODO: implement state transitions and idempotency using the existing DAO contract.
  throw new Problem(501,"NOT_IMPLEMENTED");
 }
}
'''
            if relative.endswith('Transitions.java'):
                text='''package assessment.statemachine;
import assessment.api.Order;
public final class Transitions {public static void apply(Order o,String user,String action){throw new UnsupportedOperationException("TODO: state and role rules");}}
'''
            if relative.endswith('OrderController.java'):
                text=re.sub(r'if\(!"1"\.equals\(System\.getenv\("BROKEN"\)\)&&!visible\(o,u\)\)throw new Problem\(403,"FORBIDDEN"\);','/* TODO: validate order ownership here */',text)
            if relative=='README.md':text='# 订单起始项目\n构建 mvn -B package；运行 java -jar order-application/target/order-application-1.0.0.jar。\n设置 MONGO_URI，默认 mongodb://localhost:27017/assessment。PORT默认8080。\n入口 /，健康 /healthz。成功接口返回 {code:0,data:...}，错误为HTTP错误码和{code:字符串}。\n源码包含两个待实现业务类和详情权限缺陷，见任务.md。\n'
            files[task+'/'+relative]=text
        files[task+'/compose.yaml']='services:\n  mongo:\n    image: mongo:7.0.16\n    ports: ["127.0.0.1:27017:27017"]\n  app:\n    build: .\n    ports: ["127.0.0.1:8080:8080"]\n    environment:\n      MONGO_URI: mongodb://mongo:27017/assessment\n    depends_on: [mongo]\n'
    with zipfile.ZipFile(dist/(task+'-candidate.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for name,text in files.items():z.writestr(name,text)
    print(task,len(files),'files')
manifest={'schemaVersion':'2.0','candidateId':'C20260001','submissionVersion':1,'primaryTask':'GAME','tasks':['GAME']}
with zipfile.ZipFile(dist/'candidate-exam.zip','w',zipfile.ZIP_DEFLATED) as bundle:
    bundle.writestr('开始前请读.md',common)
    bundle.writestr('submission-template/submission.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    bundle.writestr('submission-template/README.md','将所选工程目录复制到此处，和submission.json同级；修改候选人编号、版本及选题。')
    for task in ('GAME','ORDER'):
        with zipfile.ZipFile(dist/(task+'-candidate.zip')) as pack:
            for name in pack.namelist():bundle.writestr('tasks/'+task+'/'+name,pack.read(name))
    bundle.writestr('暂缓题目/WORKFLOW设计草案.md',(root/'questions/WORKFLOW/任务.md').read_text(encoding='utf-8'))
release={'version':'checks-2.0','scoring':'NOT_IMPLEMENTED','workflow':'DEFERRED','docker':'NOT_VERIFIED',
         'packs':{name:hashlib.sha256((dist/name).read_bytes()).hexdigest() for name in ('GAME-candidate.zip','ORDER-candidate.zip','candidate-exam.zip')}}
(dist/'release.json').write_text(json.dumps(release,ensure_ascii=False,indent=2),encoding='utf-8')
print(dist/'candidate-exam.zip')
