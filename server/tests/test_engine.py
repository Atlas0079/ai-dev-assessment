import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from assessment.check_engine import Client, Suite, Unknown, expect
from assessment.evaluate import evaluate


class EvidenceTests(unittest.TestCase):
    def test_statuses_do_not_turn_checker_errors_into_candidate_failures(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);c=Client('http://unused',folder/'evidence');suite=Suite(c,folder)
            def raises(error):raise error
            suite.check('pass','pass',lambda:None)
            suite.check('fail','fail',lambda:expect(False,'actual business mismatch'))
            suite.check('missing','missing',lambda:raises(Unknown('no control endpoint')))
            suite.check('bug','bug',lambda:raises(KeyError('checker problem')))
            self.assertEqual([x['status'] for x in suite.cases],['PASS','FAIL','NOT_RUN','ERROR'])
            with self.assertRaises(ValueError):suite.check('pass','duplicate',lambda:None)

    def test_workflow_missing_control_is_not_run_and_never_emits_score(self):
        with tempfile.TemporaryDirectory() as d,patch.object(Client,'call',return_value=(200,{'status':'ok'})):
            result=evaluate('WORKFLOW','http://unused',Path(d),{})
            self.assertEqual(result['status'],'CHECKED')
            self.assertEqual(result['summary'],{'PASS':1,'FAIL':0,'NOT_RUN':12,'ERROR':0})
            self.assertNotIn('score',result)

    def test_missing_game_control_is_not_zero_or_pass(self):
        with tempfile.TemporaryDirectory() as d,patch.object(Client,'call',return_value=(200,{'status':'ok'})):
            result=evaluate('GAME','http://unused',Path(d),{})
            self.assertEqual(result['summary'],{'PASS':1,'FAIL':0,'NOT_RUN':32,'ERROR':0})
            self.assertNotIn('score',result)

    def test_transport_failure_is_recorded(self):
        import urllib.error
        with tempfile.TemporaryDirectory() as d,patch('urllib.request.OpenerDirector.open',side_effect=urllib.error.URLError('offline')):
            c=Client('http://unused',Path(d))
            with self.assertRaises(Unknown):c.call('GET','/healthz')
            self.assertEqual(len(c.evidence),1)
            self.assertIn('transportError',json.loads(next(Path(d).glob('EV-*')).read_text(encoding='utf-8')))

    def test_tokens_redacted_from_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            c=Client('http://unused',Path(d));c.record({'tokens':{'A':'secret'},'response':{'playerToken':'secret2'}})
            text=next(Path(d).glob('EV-*')).read_text(encoding='utf-8')
            self.assertNotIn('secret',text);self.assertIn('REDACTED',text)

if __name__=='__main__':unittest.main()
