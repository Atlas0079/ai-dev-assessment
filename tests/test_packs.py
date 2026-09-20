import json
import unittest
import zipfile
from assessment.storage import ROOT


class PackTests(unittest.TestCase):
    def test_published_contracts_match_source(self):
        for task in ('GAME','ORDER'):
            with zipfile.ZipFile(ROOT/'dist'/f'{task}-candidate.zip') as pack:
                for path in (ROOT/'questions'/task).rglob('*'):
                    if path.is_file():
                        name=path.relative_to(ROOT/'questions'/task).as_posix()
                        self.assertEqual(pack.read(name).decode('utf-8'),path.read_text(encoding='utf-8'))

    def test_answers_and_workflow_executable_are_not_distributed(self):
        with zipfile.ZipFile(ROOT/'dist/candidate-exam.zip') as pack:
            names=pack.namelist()
            self.assertFalse(any('/references/' in n or n.endswith(('workflow.py','evaluate.py','game_checks.py','order_checks.py','rubric.py')) for n in names))
            self.assertFalse(any(n.startswith('tasks/WORKFLOW/') for n in names))
            self.assertIn('暂缓题目/WORKFLOW设计草案.md',names)
            manifest=json.loads(pack.read('submission-template/submission.json'))
            self.assertEqual(manifest['schemaVersion'],'2.0');self.assertNotIn('WORKFLOW',manifest['tasks'])
            service=next(n for n in names if n.endswith('/OrderService.java'))
            self.assertIn('NOT_IMPLEMENTED',pack.read(service).decode('utf-8'))
            transitions=next(n for n in names if n.endswith('/Transitions.java'))
            self.assertIn('UnsupportedOperationException',pack.read(transitions).decode('utf-8'))
            controller=next(n for n in names if n.endswith('/OrderController.java'))
            self.assertIn('TODO: validate order ownership',pack.read(controller).decode('utf-8'))
            self.assertNotIn('BROKEN',pack.read(controller).decode('utf-8'))

    def test_public_case_catalog_matches_checker_registration(self):
        from assessment.game_checks import game_checks
        from assessment.order_checks import order_checks
        for task,register in [('GAME',game_checks),('ORDER',order_checks)]:
            rows=[]
            register(None,lambda id,title,fn,*args:rows.append((id,title)),{})
            document=(ROOT/'questions'/task/'评分标准.md').read_text(encoding='utf-8')
            for id,title in rows:self.assertIn(f'| {id} | {title} |',document)
            self.assertEqual(len(rows),len(set(id for id,title in rows)))

if __name__=='__main__':unittest.main()
