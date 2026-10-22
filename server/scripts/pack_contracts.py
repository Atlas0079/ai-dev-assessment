"""Explicit public-file allowlists; candidate/ is the editable material source."""
import json
from pathlib import Path

from assessment.catalog import QUESTIONS, question, public_catalog
from assessment.storage import CANDIDATE_PACKS

PUBLIC_DOCS = {task: spec.public_docs for task, spec in QUESTIONS.items()}
ENVIRONMENT_FILES = ('runtime.json', 'requirements.lock', 'maven-artifacts.lock', 'python.Dockerfile',
                     'order-builder.Dockerfile', 'fixed_runtime.py')
ORDER_FILES = ('pom.xml', 'Dockerfile', 'order-api/pom.xml', 'order-application/pom.xml',
    'order-application/src/main/resources/application.properties',
    'order-application/src/main/resources/static/index.html',
    *('order-api/src/main/java/assessment/api/' + name + '.java' for name in ('ResponseMsg', 'OrderOperations', 'Order')),
    *('order-application/src/main/java/assessment/' + name + '.java' for name in (
        'Application', 'support/UserContext', 'support/ResponseAdvice', 'support/Problem', 'service/OrderService',
        'statemachine/Transitions', 'controller/OrderController', 'dao/OrderDao', 'dao/MongoOrderDao')))


def question_paths(task):
    spec = question(task)
    paths = [*spec.public_docs, 'compose.yaml']
    if spec.pack_profile in ('game', 'order'):
        paths.extend(('devtools/self_check.py', 'devtools/net.py'))
    if spec.pack_profile == 'game':
        paths.extend((task + '/app.py', task + '/Dockerfile'))
    elif spec.pack_profile == 'order':
        paths.extend(task + '/' + name for name in ORDER_FILES)
    elif spec.pack_profile == 'workflow':
        paths.extend((task + '/app.py', task + '/Dockerfile', task + '/workflow.config.json',
                      '.env.example', 'devtools/Dockerfile'))
        paths.extend('devtools/workflow_support/' + name for name in
                     ('__init__.py', 'net.py', 'business.py', 'self_check.py'))
    else:
        raise ValueError('Unknown pack profile: ' + spec.pack_profile)
    if len(paths) != len(set(paths)):
        raise ValueError('题目公开文件重复：' + task)
    return paths


def audit_candidate_files(files):
    """Reject private markers in allowlisted files; unlisted files are never read."""
    for name, value in files.items():
        if name.startswith('assessment/') or any(p in name.split('/') for p in ('catalogs', 'tests', 'references')):
            raise ValueError('Private directory in candidate pack: ' + name)
        if isinstance(value, bytes):
            try:
                text = value.decode('utf-8')
            except UnicodeError:
                continue
        else:
            text = value
        for marker in ('commit_disconnect', 'denyCompleted', 'EvaluationBusiness', 'workflow_checks', '| G01 |', '| O01 |', '| W01 |'):
            if marker in text:
                raise ValueError('Private test marker in candidate pack: ' + name)


def candidate_files(source=CANDIDATE_PACKS):
    source = Path(source).resolve()
    paths = ['README.md']
    paths.extend('environment/' + name for name in ENVIRONMENT_FILES)
    for task in QUESTIONS:
        paths.extend('tasks/' + task + '/' + name for name in question_paths(task))
    files = {}
    for name in paths:
        path = source / name
        if not path.resolve().is_relative_to(source) or path.is_symlink():
            raise ValueError('公开材料路径越界或为符号链接：' + name)
        if not path.is_file():
            raise ValueError('缺少公开材料：' + str(path))
        files[name] = path.read_bytes()
    files['题目目录.json'] = json.dumps(public_catalog(), ensure_ascii=False, indent=2).encode('utf-8')
    audit_candidate_files(files)
    return files
