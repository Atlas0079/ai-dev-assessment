"""Durable HR submissions. Uploaded code is executed only by DockerSubmission."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import threading
import traceback
import uuid
import zipfile

from .catalog import QUESTIONS
from .check_engine import Client
from .evaluate import evaluate
from .report import validate_result, write_report
from .runner import DockerSubmission, sandbox_available
from .environment import (CandidateBuildError, ContractViolation, EnvironmentUnavailable,
                          profile, roles, validate_submission, verify, version as environment_version)
from .storage import CANDIDATE_PACKS, load, safe_extract, save
from .submission import FORMAT, parse_filename, submitted_tasks

MAX_UPLOAD = 100 * 1024 * 1024
RELEASE_VERSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')
JOB_ID = re.compile(r'[a-f0-9]{32}\Z')
STATES = {'QUEUED': '排队中', 'RUNNING': '评测中', 'COMPLETED': '已完成',
          'NEEDS_ACTION': '需要核对或补交', 'PLATFORM_BLOCKED': '平台待处理',
          'REVIEW_REQUIRED': '待核实'}
OWNERS = {'candidate': '候选人', 'hr': 'HR', 'platform': '平台', 'undetermined': '待核实'}


def now():
    return datetime.now(timezone.utc).isoformat()


def issue(owner, stage, message, action, task=None, cases=None):
    return dict(owner=owner, stage=stage, message=message, action=action,
                task=task, cases=cases or [])


class RequestError(Exception):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


class SubmissionIssue(Exception):
    def __init__(self, record):
        self.record = record


def environment_issue(task):
    if not sandbox_available():
        return issue('platform', '准备环境', '评测环境尚未就绪。',
                     '请将故障编号交给技术人员，配置专用隔离执行节点后重试。', task)
    try:
        result = subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'],
                                capture_output=True, timeout=15)
        if result.returncode:
            raise RuntimeError('docker unavailable')
        verify(roles(task))
        if profile(task) == 'workflow':
            from .workflow_environment import verify_services
            verify_services()
            if not os.environ.get('DEEPSEEK_API_KEY'):
                raise EnvironmentUnavailable('WORKFLOW 真实模型凭据尚未配置，本题暂不能执行。')
    except EnvironmentUnavailable as error:
        return issue('platform', '准备环境', str(error),
                     '由部署维护人员准备或修复固定环境后重试。', task)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return issue('platform', '准备环境', '隔离执行服务暂不可用。',
                     '由技术人员恢复执行服务后重试。', task)
    return None


class JobStore:
    def __init__(self, root, packages=CANDIDATE_PACKS, runner_factory=None, readiness=None):
        self.root = Path(root).resolve()
        self.jobs = self.root / 'jobs'
        self.releases = self.root / 'releases'
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.releases.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.runner_factory = runner_factory or DockerSubmission
        self.readiness = readiness or environment_issue
        self.publish(Path(packages))

    def recover_interrupted(self):
        # Called only after the HTTP service holds the exclusive data-directory lock.
        # A restarted service never pretends an interrupted execution finished.
        for job in self.list():
            if job['state'] == 'RUNNING':
                job['issues'].append(issue('platform', '执行中断', '服务重启，本次评测未完成。',
                                           '恢复环境后点击重试；系统会保留本次记录。'))
                job['state'] = 'PLATFORM_BLOCKED'
                job['stage'] = '执行中断'
                self._save(job)

    def publish(self, packages):
        manifest = load(packages / 'release.json')
        if manifest.get('submissionFormat') != FORMAT:
            raise ValueError('题包提交规则不一致，请重新运行 build-packs.py。')
        if manifest.get('environmentVersion') != environment_version():
            raise ValueError('题包与固定环境不一致，请重新运行 build-packs.py。')
        version = manifest.get('version', '')
        if not RELEASE_VERSION.fullmatch(version):
            raise ValueError('题包版本无效')
        expected = {'candidate-exam.zip'}
        if set(manifest.get('packs', {})) != expected:
            raise ValueError('公开题包清单必须只包含完整题包 candidate-exam.zip')
        destination = self.releases / version
        existing = destination / 'release.json'
        if existing.exists() and load(existing) != manifest:
            raise ValueError('已发布版本内容不同，请增加题包版本后发布')
        blobs = {}
        for name, digest in manifest['packs'].items():
            blob = (packages / name).read_bytes()
            if hashlib.sha256(blob).hexdigest() != digest:
                raise ValueError('题包摘要不一致：' + name)
            blobs[name] = blob
        destination.mkdir(exist_ok=True)
        for name, blob in blobs.items():
            target = destination / name
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != manifest['packs'][name]:
                    raise ValueError('已发布题包损坏：' + name)
            else:
                temporary = destination / (name + '.tmp')
                temporary.write_bytes(blob)
                temporary.replace(target)
        save(existing, manifest)
        self.current_release = version

    def release_list(self):
        releases = [load(p) for p in sorted(self.releases.glob('*/release.json'), reverse=True)]
        for release in releases:
            release['submissionAllowed'] = (release.get('environmentVersion') == environment_version()
                                             and release.get('submissionFormat') == FORMAT)
        return sorted(releases, key=lambda row: row['version'] != self.current_release)

    def release_file(self, version, name):
        if not RELEASE_VERSION.fullmatch(version) or name != 'candidate-exam.zip':
            raise RequestError('题包不存在', 404)
        folder = self.releases / version
        if not (folder / 'release.json').is_file() or name not in load(folder / 'release.json')['packs']:
            raise RequestError('题包不存在', 404)
        return folder / name

    def _folder(self, job_id):
        if not JOB_ID.fullmatch(job_id):
            raise RequestError('记录不存在', 404)
        return self.jobs / job_id

    def get(self, job_id):
        path = self._folder(job_id) / 'job.json'
        if not path.is_file():
            raise RequestError('记录不存在', 404)
        return load(path)

    def get_attempt(self, job_id, attempt):
        current = self.get(job_id)
        if attempt == current['attempt']:
            return current
        path = self._folder(job_id) / 'attempts' / str(attempt) / 'record.json'
        if not 1 <= attempt < current['attempt'] or not path.is_file():
            raise RequestError('执行轮次不存在。', 404)
        return load(path)

    def list(self):
        with self.lock:
            return sorted((load(p) for p in self.jobs.glob('*/job.json')),
                          key=lambda row: row['createdAt'], reverse=True)

    def _save(self, job):
        job['updatedAt'] = now()
        save(self._folder(job['id']) / 'job.json', job)

    def _validate(self, job, source):
        def bad(message, owner='candidate', action='请候选人按题目说明补齐材料，递增提交版本后重新提交。'):
            raise SubmissionIssue(issue(owner, '材料校验', message, action))
        try:
            tasks = submitted_tasks(source)
        except ValueError as error:
            bad(str(error))
        job['tasks'] = tasks
        missing = []
        for task in tasks:
            for name in ['Dockerfile', 'README.md'] + (['workflow.config.json'] if profile(task) == 'workflow' else []):
                if not (source / task / name).is_file():
                    missing.append(task + '/' + name)
        if missing:
            bad('缺少文件：' + '、'.join(missing))
        for p in source.rglob('*'):
            if p.name in {'.git', 'node_modules', '__pycache__'}:
                bad('答案含不应提交的目录：' + p.relative_to(source).as_posix())
        for task in tasks:
            try:
                validate_submission(task, source / task)
            except (ContractViolation, UnicodeError) as error:
                bad(str(error))

    def submit(self, blob, filename, version):
        try:
            candidate_id, submission_version = parse_filename(filename)
        except ValueError as error:
            raise RequestError(str(error)) from error
        if not RELEASE_VERSION.fullmatch(version) or not (self.releases / version / 'release.json').is_file():
            raise RequestError('请选择已发布的题包版本。')
        release = load(self.releases / version / 'release.json')
        if release.get('submissionFormat') != FORMAT:
            raise RequestError('该题包的提交规则与当前服务不一致，请使用负责人重新发布的题包。', 409)
        if release.get('environmentVersion') != environment_version():
            raise RequestError('该题包的环境与当前服务不一致，请联系负责人发布并使用当前题包。', 409)
        if not blob or len(blob) > MAX_UPLOAD:
            raise RequestError('请选择不超过 100 MB 的 ZIP。', 413)
        digest = hashlib.sha256(blob).hexdigest()
        with self.lock:
            for existing in self.list():
                if (existing['candidateId'], existing['submissionVersion'], existing['releaseVersion'], existing['sha256']) == (candidate_id, submission_version, version, digest):
                    return existing, False
            job = dict(jobSchemaVersion='1.0', id=uuid.uuid4().hex, candidateId=candidate_id,
                       releaseVersion=version, environmentVersion=release['environmentVersion'],
                       sha256=digest, submissionFilename=filename, submissionVersion=submission_version, tasks=[],
                       state='RUNNING', stage='材料校验', attempt=1, results={}, issues=[],
                       createdAt=now(), updatedAt=now())
            folder = self._folder(job['id'])
            folder.mkdir()
            (folder / 'submission.zip').write_bytes(blob)
            self._save(job)
            self._admit(job)
            self._save(job)
            self.wake.set()
            return job, True

    def _admit(self, job):
        folder = self._folder(job['id'])
        try:
            blob = (folder / 'submission.zip').read_bytes()
            if hashlib.sha256(blob).hexdigest() != job['sha256']:
                raise OSError('Stored submission digest mismatch')
            safe_extract(blob, folder / 'source')
            self._validate(job, folder / 'source')
            for existing in self.list():
                if existing['id'] != job['id'] and (
                        existing['candidateId'], existing['submissionVersion']) == (job['candidateId'], job['submissionVersion']) and existing['sha256'] != job['sha256']:
                    raise SubmissionIssue(issue('hr', '材料校验', '该候选人的相同提交版本已存在其他答案。',
                                                '请核对文件；若为补交，请候选人递增版本。'))
            job.update(state='QUEUED', stage='等待执行')
        except SubmissionIssue as error:
            job.update(state='NEEDS_ACTION', issues=[error.record])
        except EnvironmentUnavailable as error:
            log = folder / 'attempts' / str(job['attempt']) / 'admission.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(traceback.format_exc(), encoding='utf-8')
            job.update(state='PLATFORM_BLOCKED', stage='材料校验', issues=[issue('platform', '材料校验',
                       str(error), '请将故障编号交给技术人员，修复固定环境后重试。')])
        except (zipfile.BadZipFile, ValueError, UnicodeError, NotImplementedError, RuntimeError):
            job.update(state='NEEDS_ACTION', issues=[issue('candidate', '材料校验',
                       'ZIP 无法读取或包含不允许的路径。', '请候选人按要求重新打包并提交。')])
        except Exception:
            log = folder / 'attempts' / str(job['attempt']) / 'admission.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(traceback.format_exc(), encoding='utf-8')
            job.update(state='PLATFORM_BLOCKED', stage='材料校验', issues=[issue('platform', '材料校验',
                       '平台未能完成材料校验。', '请将故障编号交给技术人员，恢复后点击重试。')])

    def results(self, job):
        results = []
        for task, relative in job['results'].items():
            path = (self._folder(job['id']) / relative).resolve()
            if not path.is_relative_to(self._folder(job['id']).resolve()):
                raise ValueError('结果路径无效')
            value = load(path)
            validate_result(value)
            if value['task'] != task:
                raise ValueError('结果题目不一致')
            results.append(value)
        return results

    def retry(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job['state'] not in {'PLATFORM_BLOCKED', 'REVIEW_REQUIRED'}:
                raise RequestError('这份记录当前不需要重试。', 409)
            admission = not job['tasks'] or job['submissionVersion'] is None or job['stage'] == '材料校验'
            save(self._folder(job_id) / 'attempts' / str(job['attempt']) / 'record.json', job)
            job.update(state='QUEUED', stage='等待执行', attempt=job['attempt'] + 1, results={}, issues=[])
            if admission:
                job['stage'] = '材料校验'
                self._admit(job)
            self._save(job)
            self.wake.set()
            return job

    def run_once(self):
        with self.lock:
            queued = [j for j in reversed(self.list()) if j['state'] == 'QUEUED']
            if not queued:
                return False
            job = queued[0]
            job.update(state='RUNNING', stage='准备环境')
            self._save(job)
        attempt = self._folder(job['id']) / 'attempts' / str(job['attempt'])
        attempt.mkdir(parents=True, exist_ok=True)
        try:
            if job.get('environmentVersion') != environment_version():
                raise EnvironmentUnavailable('本轮任务与当前固定环境不一致，请负责人核对题包和部署版本。')
            for task in job['tasks']:
                job['stage'] = task + '：准备环境'
                self._save(job)
                blocked = self.readiness(task)
                if blocked:
                    job['issues'].append(blocked)
                    continue
                folder = attempt / task
                folder.mkdir(exist_ok=True)
                runner = self.runner_factory(task, self._folder(job['id']) / 'source' / task, folder)
                try:
                    job['stage'] = task + '：构建与启动'
                    self._save(job)
                    runner.start()
                    client = Client(runner.url, folder / 'startup-evidence', timeout=10)
                    status, health = client.call('GET', '/healthz')
                    if status != 200 or not isinstance(health, dict) or health.get('status') != 'ok':
                        job['issues'].append(issue('undetermined', '启动检查', '应用健康检查未满足要求。',
                                                   '由技术人员核对应用与环境原因。', task))
                        continue
                    job['stage'] = task + '：执行检查'
                    self._save(job)
                    result = evaluate(task, runner.url, folder, runner.meta)
                    job['results'][task] = (folder / 'result.json').relative_to(self._folder(job['id'])).as_posix()
                    for state in ('NOT_RUN', 'ERROR'):
                        cases = [c['id'] for c in result['cases'] if c['status'] == state]
                        if cases:
                            job['issues'].append(issue('undetermined', '业务检查',
                                '部分检查未完成，原因需要核实。' if state == 'NOT_RUN' else '检查过程中出现异常。',
                                '由技术人员根据证据核实，暂不归责候选人。', task, cases))
                except CandidateBuildError as error:
                    job['issues'].append(issue('candidate', '源码编译', str(error),
                                               '请候选人使用固定环境修正源码，递增提交版本后补交。', task))
                except EnvironmentUnavailable as error:
                    (folder / 'technical.log').write_text(traceback.format_exc(), encoding='utf-8')
                    job['issues'].append(issue('platform', '准备环境', str(error),
                                               '由部署维护人员修复固定环境后重试。', task))
                except Exception:
                    (folder / 'technical.log').write_text(traceback.format_exc(), encoding='utf-8')
                    job['issues'].append(issue('undetermined', job['stage'], '本题运行未完成，原因待核实。',
                                               '请将故障编号交给技术人员，核对构建、应用和平台记录。', task))
                finally:
                    try:
                        runner.close()
                    except Exception:
                        (folder / 'cleanup.log').write_text(traceback.format_exc(), encoding='utf-8')
                        job['issues'].append(issue('platform', '清理环境', '执行资源未能完整回收。',
                                                   '请技术人员处理残留资源后再重试。', task))
                self._save(job)
            results = self.results(job)
            write_report(results, attempt / '面试官报告.md', job['candidateId'], job['tasks'],
                         {task: self._folder(job['id']) / Path(path).parent for task, path in job['results'].items()})
            job['state'] = ('PLATFORM_BLOCKED' if any(i['owner'] == 'platform' for i in job['issues']) else
                            'REVIEW_REQUIRED' if any(i['owner'] == 'undetermined' for i in job['issues']) else
                            'NEEDS_ACTION' if job['issues'] else 'COMPLETED')
            job['stage'] = '已完成' if job['state'] == 'COMPLETED' else '等待处理'
        except EnvironmentUnavailable as error:
            (attempt / 'technical.log').write_text(traceback.format_exc(), encoding='utf-8')
            job['state'] = 'PLATFORM_BLOCKED'
            job['stage'] = '准备环境'
            job['issues'].append(issue('platform', '准备环境', str(error),
                                       '请负责人核对题包与固定环境版本，处理后再重试。'))
        except Exception:
            (attempt / 'technical.log').write_text(traceback.format_exc(), encoding='utf-8')
            job['state'] = 'PLATFORM_BLOCKED'
            job['stage'] = '平台异常'
            job['issues'].append(issue('platform', '生成结果', '平台未能完成本次处理。', '请将故障编号交给技术人员。'))
        self._save(job)
        save(attempt / 'record.json', job)
        return True

    def start(self):
        if self.thread:
            return
        def work():
            while not self.stop_event.is_set():
                try:
                    if self.run_once():
                        continue
                except Exception:
                    (self.root / 'worker-error.log').write_text(traceback.format_exc(), encoding='utf-8')
                self.wake.wait(2)
                self.wake.clear()
        self.thread = threading.Thread(target=work, name='hr-evaluation', daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=5)
