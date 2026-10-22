"""Verify checks against intentionally damaged disposable copies of trusted examples."""
import argparse
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.storage import ROOT, save
from assessment.runner import Reference
from assessment.evaluate import evaluate


def mutation(relative, old, new):
    def apply(working):
        path = working / relative
        text = path.read_text(encoding='utf-8')
        if text.count(old) != 1:
            raise RuntimeError('Mutation must match exactly once: ' + relative)
        path.write_text(text.replace(old, new), encoding='utf-8')
    return apply


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.output or ROOT / '.runtime/checks' / ('defects-' + uuid.uuid4().hex[:8])
    definitions = [
        ('GAME', 'draw-does-not-add-card', 'app.py', '            draw(g, p, 1)', '            pass', 'G19'),
        ('GAME', 'private-hand-leak', 'app.py', "'drawCount': len(g['drawPile'])}",
         "'drawCount': len(g['drawPile']), 'debug': {'hands': copy.deepcopy(g['hands'])}}", 'G29'),
        ('GAME', 'no-idempotent-replay', 'app.py', "if key in g['requests']:", "if False and key in g['requests']:", 'G31'),
        ('GAME', 'skip-does-not-skip', 'app.py', "if card['value'] == 'SKIP':\n                nextp = following(g, p, 2)",
         "if card['value'] == 'SKIP':\n                nextp = following(g, p, 1)", 'G10'),
        ('ORDER', 'order-detail-access', 'order-application/src/main/java/assessment/controller/OrderController.java',
         'if(!visible(o,u))', 'if(false&&!visible(o,u))', 'O08')]
    results = []
    for task, name, path, old, new, target in definitions:
        folder = root / name
        service = Reference(task, folder, mutate=mutation(path, old, new))
        try:
            service.start()
            report = evaluate(task, service.url, folder, service.meta)
            case = next(x for x in report['cases'] if x['id'] == target)
            results.append({'defect': name, 'expectedDetection': target,
                            'actualStatus': case['status'], 'detected': case['status'] == 'FAIL'})
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
        finally:
            service.close()
    save(root / 'defect-verification.json', results)
    return 0 if all(r['detected'] for r in results) else 2


if __name__ == '__main__':
    raise SystemExit(main())
