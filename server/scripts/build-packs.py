"""Build the complete exam ZIP from editable materials. Never rewrite sources."""
import hashlib
import os
from pathlib import Path
import sys
import uuid
import zipfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from assessment.storage import CANDIDATE_PACKS, save
from scripts.pack_contracts import candidate_files
from assessment.environment import version as environment_version
from assessment.submission import FORMAT


def write_entry(archive, name, value):
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, value)


def build_packs(destination=None, *, source=None):
    source = Path(source) if source is not None else CANDIDATE_PACKS
    files = candidate_files(source)
    dist = Path(destination) if destination is not None else CANDIDATE_PACKS
    dist.mkdir(parents=True, exist_ok=True)
    target = dist / 'candidate-exam.zip'
    temporary = dist / ('candidate-exam.' + uuid.uuid4().hex + '.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for name in sorted(files):
                write_entry(bundle, name, files[name])
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    release = {'version': 'packs-2.9-filename-' + digest[:16], 'environmentVersion': environment_version(source),
               'submissionFormat': FORMAT,
               'subjective': 'NOT_ENABLED',
               'workflow': 'IMPLEMENTED_REAL_MODEL_NOT_VERIFIED', 'docker': 'NOT_VERIFIED',
               'packs': {'candidate-exam.zip': digest}}
    # Only generated artifacts are replaced, including when source == destination.
    save(dist / 'release.json', release)

    print(target)
    return release


if __name__ == '__main__':
    build_packs()
