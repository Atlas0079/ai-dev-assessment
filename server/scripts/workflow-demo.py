"""Validate the canonical trusted WORKFLOW example; fixture mode is explicit."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assessment.evaluate import evaluate
from assessment.report import write_report
from assessment.runner import Reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-model', action='store_true', help='Use a test double; does not verify a real model')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.fixture_model and not os.environ.get('DEEPSEEK_API_KEY'):
        parser.error('Set DEEPSEEK_API_KEY for real model validation, or explicitly use --fixture-model.')
    upstream = None
    if args.fixture_model:
        fixture = ROOT / 'tests/workflow_model_fixture.py'
        if not fixture.is_file():
            parser.error('模型替身辅助文件仅在维护仓库本地保留，当前工程未提供 tests/workflow_model_fixture.py。')
        spec = importlib.util.spec_from_file_location('workflow_model_fixture', fixture)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        upstream = module.respond
    folder = (args.output or ROOT / '.runtime/workflow' / uuid.uuid4().hex).resolve()
    service = Reference('WORKFLOW', folder, workflow_upstream=upstream)
    try:
        service.start()
        result = evaluate('WORKFLOW', service.url, folder, service.meta)
        write_report([result], folder / '面试官报告.md', '示例工作流_13800000003', result_sources={'WORKFLOW': folder})
        print(json.dumps({'output': str(folder), 'modelMode': service.meta['modelMode'],
                          'summary': result['summary']}, ensure_ascii=False), flush=True)
        return 2 if any(result['summary'][s] for s in ('FAIL', 'NOT_RUN', 'ERROR')) else 0
    finally:
        service.close()


if __name__ == '__main__':
    raise SystemExit(main())
