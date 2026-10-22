"""Canonical standalone internal answers, packaged under the candidate contract."""
import hashlib
import io
from pathlib import Path
import tempfile
import zipfile

from .environment import validate_submission, version
from .storage import ROOT, INTERNAL_PACKS, save
from .submission import parse_filename
from .catalog import QUESTIONS, question

FILENAMES = {task: spec.example_filename for task, spec in QUESTIONS.items() if spec.example_filename}
TASKS = tuple(FILENAMES)


def source_root(task):
    if not question(task).example_filename:
        raise ValueError('没有此题的内部示例：' + task)
    return ROOT / 'internal/examples' / (task.lower() + '-submission')


def files(task):
    root = source_root(task)
    result = {}
    for path in sorted((root / task).rglob('*')):
        if any(part in {'target', '__pycache__', '.git'} for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            raise ValueError('内部示例不允许符号链接：' + str(path))
        if path.is_file() and path.suffix != '.pyc':
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def materialize(task, destination):
    destination = Path(destination)
    for name, content in files(task).items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    validate_submission(task, destination / task)
    return destination / task


def archive(task):
    output = io.BytesIO()
    for_validation = files(task)
    with tempfile.TemporaryDirectory(prefix='example-contract-') as directory:
        materialize(task, Path(directory))
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name, content in sorted(for_validation.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, content)
    return output.getvalue()


def build_examples(destination=INTERNAL_PACKS):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    outputs = {task: archive(task) for task in QUESTIONS if question(task).example_filename}
    manifest = {'schemaVersion': '1.0', 'environmentVersion': version(), 'examples': {}}
    for task, content in outputs.items():
        name = question(task).example_filename
        candidate_id, _ = parse_filename(name)
        temporary = destination / (name + '.tmp')
        temporary.write_bytes(content)
        temporary.replace(destination / name)
        manifest['examples'][task] = {'file': name, 'sha256': hashlib.sha256(content).hexdigest(),
                                      'candidateId': candidate_id}
    save(destination / 'example-release.json', manifest)
    return manifest
