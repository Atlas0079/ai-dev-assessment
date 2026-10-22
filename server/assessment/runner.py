import os,sys,time,json,socket,subprocess,shutil,threading,uuid,hashlib,re,ipaddress
from pathlib import Path
from .storage import ROOT,load
from .evaluate import Unknown
from .environment import (CandidateBuildError, EnvironmentUnavailable, build_context, profile, roles, specification,
                          verify, version)
from workflow_support.configuration import effective_config

sys.path.insert(0,str(ROOT/'.runtime/pythonlibs'))
def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def tools():
    config=load(ROOT/'.runtime'/'tools.json') if (ROOT/'.runtime'/'tools.json').exists() else {}
    return {k:os.environ.get(k.upper(),v) for k,v in config.items()}
def wait_health(url,proc):
    import urllib.request
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(180):
        if proc.poll() is not None:raise RuntimeError('参考服务提前退出，请查看启动日志')
        try:
            with opener.open(url+'/healthz',timeout=1) as r:
                if r.status==200:return
        except Exception:pass
        time.sleep(.5)
    raise RuntimeError('服务启动超时')

class Reference:
    """Execute only canonical repository examples; never arbitrary uploaded code.

    source is accepted only after byte-for-byte comparison with the canonical
    answer, and is copied to a disposable execution directory. Production HR
    continues to use DockerSubmission; this class is for trusted validation.
    """
    def __init__(self, task, folder, *, source=None, mutate=None, workflow_upstream=None):
        self.task, self.folder = task, Path(folder).resolve()
        self.profile = profile(task)
        self.source, self.mutate = Path(source).resolve() if source is not None else None, mutate
        self.workflow_upstream = workflow_upstream
        self.proc = self.mongo = None
        self.streams, self.services = [], []
        self.port = free_port()
        self.url = 'http://127.0.0.1:' + str(self.port)
        self.meta = {'mode': 'trusted-example-defect' if mutate else 'trusted-example-local',
                     'environmentVersion': version()}

    def start(self):
        from .examples import files, materialize
        self.folder.mkdir(parents=True, exist_ok=True)
        if self.source is not None:
            expected = {name.split('/', 1)[1]: content for name, content in files(self.task).items()
                        if name.startswith(self.task + '/')}
            actual = {p.relative_to(self.source).as_posix(): p.read_bytes()
                      for p in self.source.rglob('*') if p.is_file() and not p.is_symlink()}
            if any(p.is_symlink() for p in self.source.rglob('*')) or actual != expected:
                raise ValueError('本机可信验证只执行与内部示例逐字节一致的答案，不执行外部上传代码。')
            working = self.folder / 'execution-source' / self.task
            working.mkdir(parents=True, exist_ok=False)
            for name, content in actual.items():
                path = working / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        else:
            working = materialize(self.task, self.folder / 'execution-source')
        if self.mutate:
            self.mutate(working)
        self.working = working
        env = os.environ.copy()
        upstream_key = env.pop('DEEPSEEK_API_KEY', None)
        env.update(PORT=str(self.port), PYTHONDONTWRITEBYTECODE='1')
        if self.profile == 'game':
            self.meta['controlToken'] = uuid.uuid4().hex
            env.update(EVAL_FIXTURES='1', EVAL_CONTROL_TOKEN=self.meta['controlToken'])
        elif self.profile == 'order':
            config = tools()
            java = config.get('java') or shutil.which('java')
            maven = config.get('maven') or shutil.which('mvn')
            mongod = config.get('mongod') or shutil.which('mongod')
            if not all((java, maven, mongod)):
                raise RuntimeError('可信 ORDER 验证需要 JDK8、Maven 和 MongoDB；请配置本地工具。')
            env['JAVA_HOME'] = str(Path(java).resolve().parents[1])
            command = [maven, '-o', '-B', '-q', 'package', '-DskipTests']
            if config.get('maven_repository'):
                command.append('-Dmaven.repo.local=' + config['maven_repository'])
            build = subprocess.run(command, cwd=working, env=env, capture_output=True,
                                   text=True, encoding='utf-8', errors='replace', timeout=120)
            (self.folder / 'build.log').write_text(build.stdout + build.stderr, encoding='utf-8')
            if build.returncode:
                raise RuntimeError('可信 ORDER 示例离线构建失败，参见 build.log。')
            self.command = [java, '-jar', str(working / 'order-application/target/order-application-1.0.0.jar')]
            self.dbport = free_port()
            database = self.folder / 'mongodb'
            database.mkdir()
            log = (self.folder / 'mongo.log').open('w', encoding='utf-8')
            self.streams.append(log)
            self.mongo = subprocess.Popen([mongod, '--bind_ip', '127.0.0.1', '--port', str(self.dbport),
                '--dbpath', str(database), '--setParameter', 'enableTestCommands=1', '--quiet'],
                stdout=log, stderr=subprocess.STDOUT)
            env['MONGO_URI'] = f'mongodb://127.0.0.1:{self.dbport}/assessment'
            from pymongo import MongoClient
            self.dbclient = MongoClient(env['MONGO_URI'], serverSelectionTimeoutMS=5000)
            self.dbclient.admin.command('ping')
            self.meta.update(storage='mongodb', restart=self.restart,
                injectDbFailure=lambda: self.dbclient.admin.command({'configureFailPoint': 'failCommand',
                    'mode': {'times': 1}, 'data': {'failCommands': ['update'], 'closeConnection': True}}),
                readOrder=lambda order_id: self.dbclient.assessment.orders.find_one({'_id': order_id}))
        elif self.profile == 'workflow':
            from .workflow_business import EvaluationBusiness
            from workflow_support.gateway import Gateway
            from workflow_support.net import server
            if self.workflow_upstream is None and not upstream_key:
                raise RuntimeError('未提供真实模型；可信替身验证须显式注入模型替身。')
            control, access = uuid.uuid4().hex, uuid.uuid4().hex
            business = EvaluationBusiness(control)
            gateway = Gateway(upstream_key or '', access, upstream=self.workflow_upstream,
                              events_file=self.folder / 'model-calls.json')
            self.services = [server(business, 0), server(gateway, 0)]
            for service in self.services:
                threading.Thread(target=service.serve_forever, daemon=True).start()
            config = effective_config(
                business_url=f'http://127.0.0.1:{self.services[0].server_port}',
                model_url=f'http://127.0.0.1:{self.services[1].server_port}')
            effective = self.folder / 'effective-config.json'
            effective.write_text(json.dumps(config), encoding='utf-8')
            env.update(WORKFLOW_CONFIG_PATH=str(effective.resolve()), WORKFLOW_LLM_API_KEY=access)
            self.meta.update(workflowEnabled=True, businessUrl=config['business']['base_url'],
                workflowControlToken=control, gatewayEvents=gateway.events,
                modelMode='fixture' if self.workflow_upstream is not None else 'real-deepseek')
        else:
            raise ValueError('未知内部示例：' + self.task)
        if self.profile != 'order':
            self.command = [sys.executable, str(working / 'app.py')]
        self.env = env
        self.launch()
        return self

    def launch(self):
        log = (self.folder / 'application.log').open('a', encoding='utf-8')
        self.streams.append(log)
        self.proc = subprocess.Popen(self.command, cwd=self.working, env=self.env,
                                     stdout=log, stderr=subprocess.STDOUT)
        wait_health(self.url, self.proc)

    def restart(self):
        self.proc.terminate()
        self.proc.wait(timeout=15)
        self.launch()

    def close(self):
        if hasattr(self, 'dbclient'):
            self.dbclient.close()
        for process in (self.proc, self.mongo):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for service in self.services:
            service.shutdown()
            service.server_close()
        for stream in self.streams:
            stream.close()


def sandbox_available():
    return sys.platform=='linux' and os.environ.get('ASSESSMENT_DEDICATED_SANDBOX')=='1' and bool(shutil.which('docker'))

class DockerSubmission:
    """Only enabled on an explicitly provisioned dedicated Linux evaluation VM."""
    def __init__(self,task,source,folder):
        self.task,self.source,self.folder=task,Path(source),Path(folder)
        self.profile=profile(task)
        self.names=[]
        self.network=self.egress_network=None
        self.image='assessment-'+uuid.uuid4().hex[:12]
        self.meta={'mode':'docker-submission'}
    def docker(self,*args,timeout=90):
        r=subprocess.run(['docker',*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        if r.returncode:raise RuntimeError(r.stderr[-2000:])
        return r.stdout.strip()
    def container_host(self,name):
        # The evaluator runs on this Linux Docker host. Internal networks do
        # not publish host ports; use the address on this attempt's network.
        networks=json.loads(self.docker('inspect','--format','{{json .NetworkSettings.Networks}}',name))
        try:
            address=ipaddress.ip_address(networks[self.network]['IPAddress'])
            if address.version!=4 or address.is_unspecified or address.is_loopback or address.is_multicast:
                raise ValueError('invalid container IPv4 address')
        except (KeyError,TypeError,ValueError) as error:
            raise RuntimeError('本轮容器未取得内部 IPv4 地址，请核对启动与网络记录。') from error
        return str(address)
    def start(self):
        self.folder.mkdir(parents=True,exist_ok=True)
        if not sandbox_available():raise Unknown('未配置专用Linux隔离评测节点。不会在招聘人员电脑执行外部代码。')
        verify(roles(self.task))
        if self.profile=='workflow':
            from .workflow_environment import verify_services
            self.workflow_services=verify_services()
            if not os.environ.get('DEEPSEEK_API_KEY'):
                raise EnvironmentUnavailable('WORKFLOW 真实模型凭据尚未配置，本题暂不能执行。')
        self.meta['environmentVersion']=version()
        context=build_context(self.task,self.source,self.folder/'build-context')
        # Only canonical templates and preloaded dependencies are used. No pull,
        # package installation or dependency download occurs during assessment.
        r=subprocess.run(['docker','build','--platform','linux/amd64','--pull=false',
                          '--network','none','-t',self.image,str(context)],
                         capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600)
        (self.folder/'build.log').write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:
            output=r.stdout+r.stderr
            source_errors=[line for line in output.splitlines() if re.search(r'\.java:\[\d+,\d+\]',line)]
            if self.profile=='order' and '[ERROR] COMPILATION ERROR' in output and source_errors:
                raise CandidateBuildError('固定环境编译器报告源码编译错误：'+'\n'.join(source_errors)[:1600])
            raise RuntimeError('固定模板离线构建失败，参见 build.log；原因待核实。')
        self.network='net-'+uuid.uuid4().hex[:10];self.docker('network','create','--internal',self.network)
        env=[]
        if self.profile=='order':
            db='mongo-'+uuid.uuid4().hex[:10];self.names.append(db);self.docker('run','-d','--pull=never','--platform','linux/amd64','--name',db,'--network',self.network,'--memory','512m',specification()['images']['mongo'],'--bind_ip_all','--setParameter','enableTestCommands=1');env=['-e','MONGO_URI=mongodb://'+db+':27017/assessment']
            from pymongo import MongoClient
            self.dbclient=MongoClient('mongodb://'+self.container_host(db)+':27017/assessment',serverSelectionTimeoutMS=5000)
            self.meta['injectDbFailure']=lambda:self.dbclient.admin.command({'configureFailPoint':'failCommand','mode':{'times':1},'data':{'failCommands':['update'],'closeConnection':True}})
            self.meta['readOrder']=lambda id:self.dbclient.assessment.orders.find_one({'_id':id})
        if self.profile=='game':
            self.meta['controlToken']=uuid.uuid4().hex
            env=['-e','EVAL_FIXTURES=1','-e','EVAL_CONTROL_TOKEN='+self.meta['controlToken']]
        if self.profile=='workflow':
            env=self.start_workflow()
        name='candidate-'+uuid.uuid4().hex[:10];self.names.append(name)
        self.docker('run','-d','--pull=never','--platform','linux/amd64','--name',name,'--network',self.network,'--memory','4g','--cpus','2','--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges','--read-only','--tmpfs','/tmp:rw,nosuid,size=256m','--user','10001',*env,self.image)
        self.url='http://'+self.container_host(name)+':8080'
        class Alive:
            def poll(self):return None
        wait_health(self.url,Alive())
        if self.profile=='order':self.meta['restart']=lambda:(self.docker('restart',name),wait_health(self.url,Alive()))
        return self

    def start_workflow(self):
        # Only the fixed proxy gets an egress network and the upstream key.
        # Neither the candidate nor the business service can reach the Internet.
        from .storage import save
        control,access=uuid.uuid4().hex,uuid.uuid4().hex
        business='business-'+uuid.uuid4().hex[:10]
        gateway='model-'+uuid.uuid4().hex[:10]
        image=self.workflow_services['image']
        restrictions=['--memory','512m','--cpus','1','--pids-limit','128',
                      '--cap-drop','ALL','--security-opt','no-new-privileges',
                      '--read-only','--tmpfs','/tmp:rw,nosuid,size=64m','--user','10001']
        self.names.append(business)
        self.docker('run','-d','--pull=never','--platform','linux/amd64','--name',business,
                    '--network',self.network,*restrictions,
                    '-e','WORKFLOW_CONTROL_TOKEN='+control,image,'python','-m',
                    'assessment.workflow_business','--host','0.0.0.0','--port','8091')
        self.egress_network='egress-'+uuid.uuid4().hex[:10]
        self.docker('network','create',self.egress_network)
        self.names.append(gateway)
        self.docker('run','-d','--pull=never','--platform','linux/amd64','--name',gateway,
                    '--network',self.network,*restrictions,
                    '-e','DEEPSEEK_API_KEY','-e','WORKFLOW_GATEWAY_TOKEN='+access,
                    image,'python','-m','workflow_support.gateway','--host','0.0.0.0',
                    '--port','8092','--events-file','/tmp/model-calls.json')
        self.docker('network','connect',self.egress_network,gateway)
        class Alive:
            def poll(self):return None
        business_url='http://'+self.container_host(business)+':8091'
        gateway_url='http://'+self.container_host(gateway)+':8092'
        wait_health(business_url,Alive())
        wait_health(gateway_url,Alive())
        # The submission remains intact. The evaluator supplies the documented
        # override, containing scoped endpoints and no credentials.
        config=effective_config(business_url='http://'+business+':8091',
                                model_url='http://'+gateway+':8092')
        effective=self.folder/'effective-config.json'
        save(effective,config)
        effective.chmod(0o644)

        def model_events():
            # Evidence is read from the evaluator-owned gateway, never from an
            # uploaded file or a candidate response. A missing file means no calls.
            command="from pathlib import Path; p=Path('/tmp/model-calls.json'); print(p.read_text() if p.exists() else '{\"mode\":\"real-deepseek\",\"calls\":[]}')"
            record=json.loads(self.docker('exec',gateway,'python','-c',command,timeout=15))
            if record.get('mode')!='real-deepseek' or not isinstance(record.get('calls'),list):
                raise RuntimeError('模型代理证据格式无效')
            save(self.folder/'model-calls.json',record)
            return record['calls']

        self.meta.update(workflowEnabled=True,businessUrl=business_url,
                         workflowControlToken=control,gatewayEvents=model_events,
                         modelMode='real-deepseek',workflowServicesVersion=self.workflow_services['version'])
        return ['--mount','type=bind,source='+str(effective.resolve())+',target=/run/workflow.config.json,readonly',
                '-e','WORKFLOW_CONFIG_PATH=/run/workflow.config.json','-e','WORKFLOW_LLM_API_KEY='+access]

    def close(self):
        if hasattr(self,'dbclient'):self.dbclient.close()
        errors=[]
        if callable(self.meta.get('gatewayEvents')):
            try:self.meta['gatewayEvents']()
            except Exception as error:errors.append({'command':['snapshot-model-events'],'error':str(error)})
        def remove(*args):
            try:self.docker(*args)
            except Exception as error:
                message=str(error)
                # Partial startup may leave an allocated name without a resource.
                if not any(text in message.lower() for text in ('no such container','no such image','no such network','network '+str(self.network)+' not found')):
                    errors.append({'command':list(args),'error':message})
        for name in reversed(self.names):
            remove('rm','-f','-v',name)
        if self.network:
            remove('network','rm',self.network)
        if self.egress_network:
            remove('network','rm',self.egress_network)
        remove('image','rm',self.image)
        if errors:
            from .storage import save
            save(self.folder/'cleanup-errors.json',errors)
            raise RuntimeError('隔离执行资源清理失败，参见cleanup-errors.json')
