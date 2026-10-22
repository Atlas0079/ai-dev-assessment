"""Private WORKFLOW services, prepared separately from candidate dependencies."""
import hashlib
import json
from pathlib import Path
import tempfile

from .environment import EnvironmentUnavailable, specification, verify, version
from .storage import CANDIDATE_PACKS, ROOT, load, save
from fixed_runtime import docker, image_id

INPUTS = {
    'server/assessment/workflow_business.py': ROOT / 'assessment/workflow_business.py',
    'server/workflow_support/__init__.py': ROOT / 'workflow_support/__init__.py',
    'server/workflow_support/gateway.py': ROOT / 'workflow_support/gateway.py',
    'server/workflow_support/configuration.py': ROOT / 'workflow_support/configuration.py',
    'candidate/tasks/WORKFLOW/WORKFLOW/workflow.config.json':
        CANDIDATE_PACKS / 'tasks/WORKFLOW/WORKFLOW/workflow.config.json',
    **{'candidate/tasks/WORKFLOW/devtools/workflow_support/' + name:
       CANDIDATE_PACKS / 'tasks/WORKFLOW/devtools/workflow_support' / name
       for name in ('__init__.py', 'business.py', 'net.py')},
}
RECORD = ROOT / '.runtime/workflow-environment.json'
DOCKERFILE = '''FROM {base}
WORKDIR /opt/assessment/server
COPY server /opt/assessment/server
COPY candidate /opt/assessment/candidate
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001
'''


def service_version():
    digest = hashlib.sha256(version().encode())
    digest.update(Path(__file__).read_bytes().replace(b'\r\n', b'\n'))
    for name, path in sorted(INPUTS.items()):
        digest.update(name.encode() + b'\0' + path.read_bytes().replace(b'\r\n', b'\n') + b'\0')
    return 'workflow-1-' + digest.hexdigest()[:16]


def verify_services():
    try:
        record = load(RECORD)
        expected = service_version()
        if (record.get('version') != expected or record.get('verified') is not True
                or record.get('image') != 'assessment-workflow-services:' + expected
                or record.get('imageId') != image_id(record['image'])):
            raise ValueError('services changed')
        return record
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise EnvironmentUnavailable('WORKFLOW 内部服务镜像尚未准备或已变化，请重新运行 prepare-environment.py。') from error


def prepare_services():
    verify(('python',))
    RECORD.parent.mkdir(exist_ok=True)
    RECORD.unlink(missing_ok=True)
    current = service_version()
    image = 'assessment-workflow-services:' + current
    with tempfile.TemporaryDirectory(prefix='workflow-prepare-', dir=RECORD.parent) as directory:
        context = Path(directory)
        for name, source in INPUTS.items():
            path = context / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
        (context / 'server/assessment/__init__.py').write_text('', encoding='utf-8')
        (context / 'Dockerfile').write_text(DOCKERFILE.format(base=specification()['images']['python']), encoding='utf-8')
        docker('build', '--platform', 'linux/amd64', '--pull=false', '--network', 'none',
               '-t', image, str(context), timeout=180)
        docker('run', '--rm', '--pull=never', '--network', 'none', image, 'python', '-c',
               "from assessment.workflow_business import EvaluationBusiness; "
               "from workflow_support.gateway import Gateway; "
               "b=EvaluationBusiness('probe'); "
               "assert b('POST','/__control/reset',{},'probe',None)[0]==200; "
               "assert Gateway('unused','probe')('GET','/healthz',{},'',None)[0]==200")
    record = {'version': current, 'image': image, 'imageId': image_id(image), 'verified': True}
    save(RECORD, record)
    print('WORKFLOW 内部服务准备完成：' + current, flush=True)
    return record
