"""Admission rules and trusted build contexts for the public fixed environment."""
import ast
from pathlib import Path
import re
import shutil
import sys

from .catalog import question
from .storage import CANDIDATE_PACKS

sys.path.insert(0, str(CANDIDATE_PACKS / 'environment'))
from fixed_runtime import EnvironmentUnavailable, specification, verify, version


class ContractViolation(ValueError):
    """An observed violation of the published submission contract."""


class CandidateBuildError(RuntimeError):
    """The fixed offline compiler reported explicit source compilation errors."""


def profile(task):
    return question(task).pack_profile


def protected_files(task):
    if profile(task) == 'order':
        return ('Dockerfile', 'pom.xml', 'order-api/pom.xml', 'order-application/pom.xml')
    return ('Dockerfile',)


def template(task, name):
    question(task)
    return CANDIDATE_PACKS / 'tasks' / task / task / name


def roles(task):
    return ('order-builder', 'java', 'mongo') if profile(task) == 'order' else ('python',)


def normalized(path):
    return path.read_text(encoding='utf-8-sig').replace('\r\n', '\n').strip()


def validate_submission(task, source):
    source = Path(source)
    kind = profile(task)
    for name in protected_files(task):
        path = source / name
        try:
            expected = normalized(template(task, name))
        except (OSError, UnicodeError) as error:
            raise EnvironmentUnavailable('服务端固定模板不可读，请部署维护人员修复。') from error
        if not path.is_file() or normalized(path) != expected:
            raise ContractViolation(task + '/' + name + ' 是固定环境配置，请恢复题包原文件。')
    if kind != 'order' and not (source / 'app.py').is_file():
        raise ContractViolation(task + '/app.py 缺失；固定启动入口为 python app.py。')
    permitted = {'.md', '.py', '.html', '.css', '.js', '.json', '.txt', '.svg',
                 '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico'}
    if kind == 'order':
        permitted = (permitted - {'.py'}) | {'.java', '.properties', '.xml'}
    forbidden_dirs = {'.git', '.mvn', '.venv', 'venv', 'node_modules', '__pycache__',
                      'site-packages', 'vendor', 'target', 'dist', 'build'}
    paths = sorted(p for p in source.rglob('*') if p.is_file() or p.is_symlink())
    local_modules = {p.stem for p in source.glob('*.py')}
    local_modules.update(p.name for p in source.iterdir() if p.is_dir())
    allowed_imports = set(sys.stdlib_module_names) | set(specification()['pythonModules']) | local_modules
    for path in paths:
        name = path.relative_to(source).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
            raise ContractViolation('不允许符号链接或越界路径：' + task + '/' + name)
        if any(part.lower() in forbidden_dirs for part in path.relative_to(source).parts):
            raise ContractViolation('不允许依赖目录或构建产物：' + task + '/' + name)
        if name in protected_files(task):
            continue
        lower = path.name.lower()
        if (path.suffix.lower() not in permitted or lower.startswith(('requirements', 'pipfile', 'poetry.lock'))
                or lower in {'package.json', 'package-lock.json', 'pom.xml', 'pyproject.toml',
                             'setup.py', 'setup.cfg', 'uv.lock', 'environment.yml', 'environment.yaml'}):
            raise ContractViolation('固定环境不接受额外依赖、安装脚本或此类文件：' + task + '/' + name)
        if path.suffix.lower() in {'.py', '.js', '.html', '.css'}:
            try:
                text = path.read_text(encoding='utf-8-sig')
            except UnicodeError as error:
                raise ContractViolation('源码须使用 UTF-8：' + task + '/' + name) from error
            if path.suffix.lower() == '.py':
                try:
                    tree = ast.parse(text, filename=name)
                except SyntaxError as error:
                    raise ContractViolation(f'{task}/{name}:{error.lineno} 存在 Python 语法错误：{error.msg}') from error
                for node in ast.walk(tree):
                    names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                             else [node.module] if isinstance(node, ast.ImportFrom) and not node.level and node.module else [])
                    for imported in names:
                        if imported.split('.')[0] not in allowed_imports:
                            raise ContractViolation(f'{task}/{name}:{node.lineno} 引用了固定环境外的库：{imported}')
            elif re.search(r'''(?:\b(?:src|href)\s*=\s*["']\s*(?:https?:)?//|@import\s+["'](?:https?:)?//|url\(\s*["']?(?:https?:)?//)''', text, re.I):
                # Restrict resource attributes; ordinary business/model URLs in
                # JavaScript strings are not themselves dependency declarations.
                raise ContractViolation('页面资源须随源码提供，不能使用外部链接或 CDN：' + task + '/' + name)
            elif path.suffix.lower() == '.js' and re.search(
                    r'''(?:\bfrom\s*["']|\b(?:import|require)\s*\(?\s*["'])(?!\.{1,2}/|/)[^"']+["']''', text):
                raise ContractViolation('前端只使用原生 JavaScript 和本地资源：' + task + '/' + name)


def build_context(task, source, destination):
    """Never use the uploaded Dockerfile, Maven configuration or ignore rules."""
    validate_submission(task, source)
    source, destination = Path(source), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for path in source.rglob('*'):
        if path.is_file():
            relative = path.relative_to(source)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    for name in protected_files(task):
        shutil.copyfile(template(task, name), destination / name)
    return destination
