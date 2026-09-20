import os,sys,time,json,socket,subprocess,shutil,threading,uuid,hashlib
from pathlib import Path
from .storage import ROOT,load
from .evaluate import Unknown

sys.path.insert(0,str(ROOT/'.runtime/pythonlibs'))
def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def tools():
    config=load(ROOT/'.runtime'/'tools.json') if (ROOT/'.runtime'/'tools.json').exists() else {}
    return {k:os.environ.get(k.upper(),v) for k,v in config.items()}
def wait_health(url,proc):
    import urllib.request
    for _ in range(180):
        if proc.poll() is not None:raise RuntimeError('参考服务提前退出，请查看启动日志')
        try:
            with urllib.request.urlopen(url+'/healthz',timeout=1) as r:
                if r.status==200:return
        except Exception:pass
        time.sleep(.5)
    raise RuntimeError('服务启动超时')

class Reference:
    def __init__(self,task,folder,broken=False):self.task=task;self.folder=folder;self.broken=broken;self.proc=None;self.mongo=None;self.toolproc=None;self.streams=[];self.port=free_port();self.url='http://127.0.0.1:'+str(self.port)
    def start(self):
        if self.task not in ('GAME','ORDER'):raise ValueError('WORKFLOW deferred; no executable assessment')
        self.folder.mkdir(parents=True,exist_ok=True)
        env=os.environ.copy();env.update(PORT=str(self.port),EVAL_FIXTURES='1',BROKEN='1' if self.broken else '0')
        self.meta={'mode':'trusted-reference'}
        if self.task=='GAME':
            self.meta['controlToken']=uuid.uuid4().hex;env['EVAL_CONTROL_TOKEN']=self.meta['controlToken']
        if self.task=='ORDER':
            config=tools();java=config.get('java') or shutil.which('java');jar=ROOT/'order-reference/order-application/target/order-application-1.0.0.jar'
            if not java or not jar.exists():raise RuntimeError('需要Java8并先构建订单参考项目；运行 scripts/bootstrap.ps1')
            self.command=[java,'-jar',str(jar)]
            mongo=config.get('mongod') or shutil.which('mongod')
            if mongo:
                self.dbport=free_port();db=self.folder/'mongodb';db.mkdir(parents=True,exist_ok=True);log=open(self.folder/'mongo.log','w',encoding='utf-8');self.streams.append(log)
                self.mongo=subprocess.Popen([mongo,'--bind_ip','127.0.0.1','--port',str(self.dbport),'--dbpath',str(db),'--setParameter','enableTestCommands=1','--quiet'],stdout=log,stderr=subprocess.STDOUT)
                env['MONGO_URI']=f'mongodb://127.0.0.1:{self.dbport}/assessment';self.meta['restart']=self.restart;self.meta['storage']='mongodb'
                try:
                    from pymongo import MongoClient
                    self.dbclient=MongoClient(env['MONGO_URI'],serverSelectionTimeoutMS=4000)
                    self.meta['injectDbFailure']=lambda:self.dbclient.admin.command({'configureFailPoint':'failCommand','mode':{'times':1},'data':{'failCommands':['update'],'closeConnection':True}})
                    self.meta['readOrder']=lambda id:self.dbclient.assessment.orders.find_one({'_id':id})
                except ImportError:pass
                time.sleep(1)
            else:raise RuntimeError('MongoDB unavailable; memory fallback is disabled')
        else:
            self.command=[sys.executable,str(ROOT/'references/game.py')]
        self.env=env;self.launch();return self
    def launch(self):
        log=open(self.folder/'application.log','a',encoding='utf-8');self.streams.append(log);self.proc=subprocess.Popen(self.command,cwd=ROOT,env=self.env,stdout=log,stderr=subprocess.STDOUT);wait_health(self.url,self.proc)
    def restart(self):
        self.proc.terminate();self.proc.wait(timeout=15);self.launch()
    def close(self):
        if hasattr(self,'dbclient'):self.dbclient.close()
        for p in [self.proc,self.mongo,self.toolproc]:
            if p and p.poll() is None:
                p.terminate()
                try:p.wait(timeout=12)
                except subprocess.TimeoutExpired:p.kill();p.wait()
        for f in self.streams:f.close()

def sandbox_available():
    return sys.platform=='linux' and os.environ.get('ASSESSMENT_DEDICATED_SANDBOX')=='1' and bool(shutil.which('docker'))

class DockerSubmission:
    """Only enabled on an explicitly provisioned dedicated Linux evaluation VM."""
    def __init__(self,task,source,folder):self.task=task;self.source=source;self.folder=folder;self.names=[];self.network=None;self.image='assessment-'+uuid.uuid4().hex[:12];self.meta={'mode':'docker-submission'}
    def docker(self,*args,timeout=90):
        r=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=timeout)
        if r.returncode:raise RuntimeError(r.stderr[-2000:])
        return r.stdout.strip()
    def start(self):
        if self.task not in ('GAME','ORDER'):raise ValueError('WORKFLOW deferred')
        self.folder.mkdir(parents=True,exist_ok=True)
        if not sandbox_available():raise Unknown('未配置专用Linux隔离评测节点。不会在招聘人员电脑执行外部代码。')
        # Build occurs inside the dedicated VM, never on the operator host.
        r=subprocess.run(['docker','build','--network',os.environ.get('ASSESSMENT_BUILD_NETWORK','default'),'-t',self.image,str(self.source)],capture_output=True,text=True,timeout=600)
        (self.folder/'build.log').write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise RuntimeError('候选人构建失败，参见build.log（需复核依赖网络归因）')
        self.network='net-'+uuid.uuid4().hex[:10];self.docker('network','create','--internal',self.network)
        env=[]
        if self.task=='ORDER':
            db='mongo-'+uuid.uuid4().hex[:10];self.names.append(db);self.docker('run','-d','--name',db,'--network',self.network,'--memory','512m','-p','127.0.0.1::27017','mongo:7.0.16','--bind_ip_all','--setParameter','enableTestCommands=1');env=['-e','MONGO_URI=mongodb://'+db+':27017/assessment']
            from pymongo import MongoClient
            dbport=self.docker('port',db,'27017').split(':')[-1];self.dbclient=MongoClient('mongodb://127.0.0.1:'+dbport+'/assessment',serverSelectionTimeoutMS=5000)
            self.meta['injectDbFailure']=lambda:self.dbclient.admin.command({'configureFailPoint':'failCommand','mode':{'times':1},'data':{'failCommands':['update'],'closeConnection':True}})
            self.meta['readOrder']=lambda id:self.dbclient.assessment.orders.find_one({'_id':id})
        if self.task=='GAME':
            self.meta['controlToken']=uuid.uuid4().hex
            env=['-e','EVAL_FIXTURES=1','-e','EVAL_CONTROL_TOKEN='+self.meta['controlToken']]
        name='candidate-'+uuid.uuid4().hex[:10];self.names.append(name)
        self.docker('run','-d','--name',name,'--network',self.network,'--memory','4g','--cpus','2','--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges','--read-only','--tmpfs','/tmp:rw,nosuid,size=256m','--user','10001','-p','127.0.0.1::8080',*env,self.image)
        port=self.docker('port',name,'8080').split(':')[-1];self.url='http://127.0.0.1:'+port
        class Alive:
            def poll(self):return None
        wait_health(self.url,Alive())
        if self.task=='ORDER':self.meta['restart']=lambda:(self.docker('restart',name),wait_health(self.url,Alive()))
        return self
    def close(self):
        if hasattr(self,'dbclient'):self.dbclient.close()
        for name in reversed(self.names):
            try:self.docker('rm','-f',name)
            except Exception:pass
        if self.network:
            try:self.docker('network','rm',self.network)
            except Exception:pass
        try:self.docker('image','rm',self.image)
        except Exception:pass
