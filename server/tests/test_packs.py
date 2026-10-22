import json
import contextlib
import importlib.util
import io
import tempfile
from pathlib import Path
import unittest
import zipfile
from assessment.storage import ROOT, CANDIDATE_PACKS
from scripts.pack_contracts import PUBLIC_DOCS


class PackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='pack-tests-')
        cls.addClassCleanup(cls.temporary.cleanup)
        spec = importlib.util.spec_from_file_location('pack_test_builder', ROOT/'scripts/build-packs.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with contextlib.redirect_stdout(io.StringIO()):
            builder.build_packs(cls.temporary.name)
        cls.pack = Path(cls.temporary.name)/'candidate-exam.zip'

    def test_published_contracts_match_source(self):
        for task in ('GAME','ORDER','WORKFLOW'):
            with zipfile.ZipFile(self.pack) as pack:
                for name in PUBLIC_DOCS[task]:
                    self.assertEqual(pack.read('tasks/'+task+'/'+name).decode('utf-8'),
                                     (CANDIDATE_PACKS/'tasks'/task/name).read_text(encoding='utf-8'))

    def test_answers_are_separate_from_public_workflow_tools(self):
        with zipfile.ZipFile(self.pack) as pack:
            names=pack.namelist()
            self.assertFalse(any('/references/' in n or n.endswith(('workflow.py','evaluate.py','game_checks.py','order_checks.py','rubric.py')) for n in names))
            self.assertTrue(any(n.startswith('tasks/WORKFLOW/') for n in names))
            self.assertIn('tasks/WORKFLOW/devtools/workflow_support/business.py',names)
            self.assertNotIn('暂缓题目/WORKFLOW设计草案.md',names)
            self.assertNotIn('propose_application',pack.read('tasks/WORKFLOW/WORKFLOW/app.py').decode('utf-8'))
            self.assertFalse(any(n.endswith(('workflow_checks.py','workflow_model_fixture.py','gateway.py')) for n in names))
            self.assertFalse(any('submission-template/' in name or name.endswith('submission.json') for name in names))
            self.assertIn('姓名_报名手机号_v1.zip', pack.read('README.md').decode('utf-8'))
            service=next(n for n in names if n.endswith('/OrderService.java'))
            self.assertIn('NOT_IMPLEMENTED',pack.read(service).decode('utf-8'))
            transitions=next(n for n in names if n.endswith('/Transitions.java'))
            self.assertIn('UnsupportedOperationException',pack.read(transitions).decode('utf-8'))
            controller=next(n for n in names if n.endswith('/OrderController.java'))
            self.assertIn('TODO: validate order ownership',pack.read(controller).decode('utf-8'))
            self.assertNotIn('BROKEN',pack.read(controller).decode('utf-8'))

    def test_internal_checker_registration_has_unique_ids(self):
        from assessment.catalog import QUESTIONS, question
        for task in QUESTIONS:
            rows=[]
            from types import SimpleNamespace
            question(task).checker(SimpleNamespace(folder=ROOT/'.runtime/test-catalog'),lambda id,title,fn,*args:rows.append((id,title)),{})
            self.assertEqual(len(rows),len(set(id for id,title in rows)))

if __name__=='__main__':unittest.main()
