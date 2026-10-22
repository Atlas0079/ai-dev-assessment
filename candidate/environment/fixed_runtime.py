"""Public fixed environment: prepare once, verify before offline assessments."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
CANDIDATE = ROOT.parent
PROTECTED = ('Dockerfile', 'pom.xml', 'order-api/pom.xml', 'order-application/pom.xml')
INPUTS = ('environment/runtime.json', 'environment/requirements.lock',
          'environment/maven-artifacts.lock',
          'environment/python.Dockerfile', 'environment/order-builder.Dockerfile',
          'environment/fixed_runtime.py', 'tasks/GAME/GAME/Dockerfile',
          'tasks/WORKFLOW/WORKFLOW/Dockerfile',
          *('tasks/ORDER/ORDER/' + name for name in PROTECTED))


class EnvironmentUnavailable(RuntimeError):
    pass


def specification():
    try:
        data = json.loads((ROOT / 'runtime.json').read_text(encoding='utf-8'))
        if data['platform'] != 'linux/amd64' or not all('@sha256:' in ref for ref in data['bases'].values()):
            raise ValueError('invalid fixed image manifest')
        return data
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise EnvironmentUnavailable('固定环境清单无效，请部署维护人员修复。') from error


def version(candidate=CANDIDATE):
    digest = hashlib.sha256()
    for name in INPUTS:
        digest.update(name.encode() + b'\0')
        # Git checkout line endings do not change the environment contract.
        digest.update((Path(candidate) / name).read_bytes().replace(b'\r\n', b'\n') + b'\0')
    return 'fixed-1-' + digest.hexdigest()[:16]


def docker(*args, timeout=90):
    try:
        run = subprocess.run(['docker', *args], capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise EnvironmentUnavailable('Docker 无法调用；请部署维护人员检查。') from error
    if run.returncode:
        raise EnvironmentUnavailable('Docker 命令失败：' + run.stderr[-2000:])
    return run.stdout.strip()


def image_id(reference):
    try:
        data = json.loads(docker('image', 'inspect', reference))[0]
        if (data.get('Os'), data.get('Architecture')) != ('linux', 'amd64'):
            raise ValueError('wrong platform')
        return data['Id']
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise EnvironmentUnavailable('固定镜像身份或平台无效：' + reference) from error


def verify(roles=None):
    path = ROOT / '.runtime/prepared.json'
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise EnvironmentUnavailable('固定环境尚未准备，请运行 prepare-environment.py。') from error
    if record.get('version') != version() or record.get('offlineVerified') is not True:
        raise EnvironmentUnavailable('固定环境与当前题包不一致，请重新准备环境。')
    expected = specification()['images']
    for role in roles if roles is not None else expected:
        reference = expected[role]
        if record.get('images', {}).get(role) != image_id(reference):
            raise EnvironmentUnavailable('固定镜像缺失或内容变化，请重新准备环境：' + role)
    return record


def prepare():
    spec = specification()
    docker('info', '--format', '{{.ServerVersion}}')
    work = ROOT / '.runtime'
    work.mkdir(exist_ok=True)
    # A failed preparation must never retain a success marker for this run.
    (work / 'prepared.json').unlink(missing_ok=True)
    for reference in spec['bases'].values():
        docker('pull', '--platform', 'linux/amd64', reference, timeout=900)
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=work) as directory:
        context = Path(directory)
        for name in ('requirements.lock', 'maven-artifacts.lock', 'python.Dockerfile', 'order-builder.Dockerfile'):
            (context / name).write_text((ROOT / name).read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
        shutil.copytree(CANDIDATE / 'tasks/ORDER/ORDER', context / 'ORDER',
                        ignore=shutil.ignore_patterns('target', '.git', '__pycache__'))
        for role, template, base in (
                ('python', 'python.Dockerfile', 'python'),
                ('order-builder', 'order-builder.Dockerfile', 'maven')):
            print('准备固定镜像：' + role, flush=True)
            docker('build', '--platform', 'linux/amd64', '--pull=false',
                   '--build-arg', 'BASE_IMAGE=' + spec['bases'][base],
                   '-f', str(context / template), '-t', spec['images'][role],
                   str(context), timeout=1200)
        # Verify the prepared dependency cache with the same offline build used
        # for submissions, using only the public trusted starter project.
        probe = context / 'offline-probe'
        shutil.copytree(context / 'ORDER', probe)
        probe_image = 'assessment-environment-probe:' + version()
        try:
            docker('build', '--platform', 'linux/amd64', '--pull=false',
                   '--network', 'none', '-t', probe_image, str(probe), timeout=600)
            docker('run', '--rm', '--pull=never', '--network', 'none',
                   spec['images']['python'], 'python', '-c',
                   "import fastapi,uvicorn,httpx; from fastapi import FastAPI; "
                   "from fastapi.testclient import TestClient; "
                   "app=FastAPI(); app.get('/healthz')(lambda:{'status':'ok'}); "
                   "assert TestClient(app).get('/healthz').json()=={'status':'ok'}; "
                   "assert httpx.Client(trust_env=False).is_closed is False")
        finally:
            try:
                docker('image', 'rm', probe_image)
            except EnvironmentUnavailable:
                # A failed build may not have created an image; preserve the
                # preparation error rather than replacing it with "not found".
                if docker('image', 'ls', '-q', probe_image):
                    raise
    record = {'version': version(), 'offlineVerified': True,
              'images': {role: image_id(ref) for role, ref in spec['images'].items()}}
    temporary = work / 'prepared.tmp'
    temporary.write_text(json.dumps(record, indent=2), encoding='utf-8')
    temporary.replace(work / 'prepared.json')
    print('固定环境准备完成：' + record['version'], flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify'), nargs='?', default='prepare')
    args = parser.parse_args()
    try:
        if args.action == 'prepare':
            prepare()
        else:
            print(json.dumps(verify(), ensure_ascii=False, indent=2))
    except EnvironmentUnavailable as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
