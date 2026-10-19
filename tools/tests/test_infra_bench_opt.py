import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1] / 'infra_bench_opt.py'
spec = importlib.util.spec_from_file_location('opt_results', TOOL)
opt = importlib.util.module_from_spec(spec);spec.loader.exec_module(opt)
assert Path(opt.__file__).resolve() == TOOL


def result(kind='baseline', score=1.0):
    return {'schema_version':opt.SCHEMA, 'benchmark':'infra-bench-opt', 'task_id':'example',
            'kind':kind, 'status':'BASELINE_VALIDATED' if kind=='baseline' else 'VALID',
            'valid':True, 'score':score, 'improvement_pct':(score-1)*100, 'completed_at':100.0}


class OptTests(unittest.TestCase):
    def test_continuous_scores_not_binary(self):
        for score in (.95,1,1.02,1.5,2.1):self.assertEqual(opt.validate(result('candidate',score))['score'],score)

    def test_invalid_has_no_numeric_score(self):
        x=result('candidate');x.update(valid=False,status='INVALID')
        with self.assertRaises(ValueError):opt.validate(x)
        x.update(score=None,improvement_pct=None);opt.validate(x)

    def test_nonfinite_scores_rejected(self):
        for score in (float('nan'),float('inf'),0,-1,True):
            with self.assertRaises(ValueError):opt.validate(result('candidate',score))

    def test_binary_result_cannot_enter_track(self):
        with self.assertRaises(ValueError):opt.validate({'reward':1,'status':'PASSED'})

    def run_campaign(self, root):
        baseline=root/'base.json';baseline.write_text(json.dumps(result()))
        with patch.object(opt.time,'time',return_value=1000):state=opt.start(root/'campaign','example',baseline,100,method='fixture-v1')
        return state

    def record_at(self, root, state, score, completion, receipt):
        with patch.object(opt.time,'time',return_value=min(completion-1,state['deadline']-1)):
            trial=opt.begin(root/'campaign','a'*64)
        x=result('candidate',score);x['trial_id']=trial['trial_id'];x.update(campaign_id=state['campaign_id'],baseline_sha256=state['baseline_sha256'],timed=True,deadline=state['deadline'],completed_at=completion,source_sha256='a'*64)
        path=root/(str(completion)+'.json');path.write_text(json.dumps(x))
        with patch.object(opt.time,'time',return_value=receipt):return opt.record(root/'campaign',path)

    def test_best_within_budget_retains_regressions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=self.run_campaign(root)
            a=self.record_at(root,state,.95,1010,1011);self.assertTrue(a['valid']);self.assertEqual(a['score'],.95)
            self.assertTrue(opt.summarize(root/'campaign')['baseline_fallback'])
            self.record_at(root,state,1.02,1020,1021)
            self.record_at(root,state,1.5,1040,1041)
            late=self.record_at(root,state,2.0,1110,1111);self.assertEqual(late['status'],'LATE');self.assertIsNone(late['score'])
            summary=opt.summarize(root/'campaign');self.assertEqual(summary['best']['score'],1.5)
            self.assertEqual(summary['counts']['VALID'],3);self.assertEqual(summary['counts']['LATE'],1)

    def test_backdated_late_receipt_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=self.run_campaign(root)
            self.assertFalse(self.record_at(root,state,3.0,1010,1101)['valid'])
            self.assertEqual(opt.summarize(root/'campaign')['best']['score'],1)

    def test_duplicate_and_changed_baseline_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=self.run_campaign(root);self.record_at(root,state,1.1,1010,1011)
            with patch.object(opt.time,'time',return_value=1012):
                with self.assertRaises(ValueError):opt.record(root/'campaign',root/'1010.json')
            (root/'campaign/baseline.json').write_text('{}')
            with self.assertRaises(ValueError):opt.summarize(root/'campaign')

    def test_leaderboard_is_continuous_and_requires_finished_campaign(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=self.run_campaign(root);self.record_at(root,state,1.02,1010,1011)
            with patch.object(opt.time,'time',return_value=1020):
                with self.assertRaises(ValueError):opt.leaderboard([root/'campaign'])
            with patch.object(opt.time,'time',return_value=1200):
                board=opt.leaderboard([root/'campaign'])
                self.assertEqual(board['ranking'][0]['median_score'],1.02)
                with self.assertRaises(ValueError):opt.leaderboard([root/'campaign',root/'campaign'])

    def test_ledger_score_cannot_override_stored_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=self.run_campaign(root);self.record_at(root,state,1.02,1010,1011)
            ledger=root/'campaign/events.jsonl';event=json.loads(ledger.read_text());event['score']=9.0
            ledger.write_text(json.dumps(event)+'\n')
            with self.assertRaises(ValueError):opt.summarize(root/'campaign')

    def test_wrong_campaign_or_modified_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=self.run_campaign(root)
            self.record_at(root,state,1.02,1010,1011)
            value=json.loads((root/'1010.json').read_text())
            with patch.object(opt.time,'time',return_value=1020):
                receipt=opt.begin(root/'campaign','a'*64)
            value.update(trial_id=receipt['trial_id'],completed_at=1021,campaign_id='f'*32)
            candidate=root/'new.json';candidate.write_text(json.dumps(value))
            with patch.object(opt.time,'time',return_value=1022):
                with self.assertRaisesRegex(ValueError,'Different campaign'):opt.record(root/'campaign',candidate)
                value['campaign_id']=state['campaign_id'];candidate.write_text(json.dumps(value))
                receipt_path=Path(receipt.pop('receipt_path'));receipt['baseline_sha256']='0'*64
                receipt_path.write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError,'Trial receipt'):opt.record(root/'campaign',candidate)

    def test_missing_and_corrupted_result_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=self.run_campaign(root);event=self.record_at(root,state,1.1,1010,1011)
            (root/'campaign'/(event['result_sha256']+'.json')).write_text('{}')
            with self.assertRaises(ValueError):opt.summarize(root/'campaign')


if __name__=='__main__':unittest.main()
