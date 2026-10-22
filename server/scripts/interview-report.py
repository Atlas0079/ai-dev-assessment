"""Combine current objective results; leave subjective advice empty."""
import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.report import write_report
from assessment.storage import safe_extract
from assessment.submission import parse_filename, submitted_tasks

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--submission', type=Path, required=True, help='姓名_报名手机号_v1.zip 格式的原始答案包')
p.add_argument('--result', type=Path, action='append', default=[])
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
try:
    candidate_id, _ = parse_filename(a.submission.name)
    with tempfile.TemporaryDirectory(prefix='interview-report-') as directory:
        safe_extract(a.submission.read_bytes(), directory)
        tasks = submitted_tasks(directory)
    results = [json.loads(path.read_text(encoding='utf-8-sig')) for path in a.result]
    write_report(results, a.output, candidate_id, tasks,
                 result_sources={result['task']:path.parent for result,path in zip(results,a.result)})
except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as error:
    p.error(str(error))
print(a.output)
