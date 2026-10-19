"""Synthetic protocol controls, not model or performance acceptance evidence."""
import copy
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import sys
import unittest
import tempfile
import json
import subprocess
from unittest.mock import patch
from types import SimpleNamespace
import time
import hashlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
import score
import performance
import evaluate
import check_assets
import verify
assert Path(score.__file__).resolve().is_relative_to(ROOT)
assert Path(verify.__file__).resolve().is_relative_to(ROOT)


def reports():
    quality = {'status': 'PASSED', 'passed': 100, 'total': 100, 'model': 'Qwen3.6-27B',
               'contract': {'fixture': True}, 'results': [{'id': str(i), 'passed': True} for i in range(100)]}
    perf = {'status': 'MEASURED', 'compilation_clean_verified': True, 'model': quality['model'],
            'contract': {'workload': dict(performance.DEFAULTS)}, 'cases': [],
            'server_info': {'dtype': 'bfloat16', 'kv_cache_dtype': 'bfloat16', 'mamba_ssm_dtype': 'bfloat16',
                            'tp_size': 2, 'context_length': 67584, 'disable_radix_cache': True,
                            'disable_cuda_graph': False, 'speculative_algorithm': None}}
    for length in performance.DEFAULTS['input_lengths']:
        rows = [{'status': 'SUCCEEDED', 'input_tokens': length, 'output_tokens': 1024,
                 'ttft_ms': 1.0, 'tpot_ms': 2.0} for _ in range(performance.DEFAULTS['requests'])]
        perf['cases'].append({'input_length': length, 'output_length': 1024, 'prompts_sha256': str(length),
                              'rounds': [performance.summarize(rows, 10) for _ in range(3)],
                              'pooled': performance.summarize(rows * 3, 30)})
    return quality, perf


def baseline_report(q, p, env):
    value = score.initial_result('baseline')
    value.update(valid=True, score=1.0, improvement_pct=0.0, status='BASELINE_VALIDATED',
                 quality=q, performance=p, environment=env)
    return value


class VerifierTests(unittest.TestCase):
    def test_model_asset_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / 'model.safetensors.index.json'
            index.write_text(json.dumps({'weight_map': {'weight': 'part.safetensors'}}))
            shard = root / 'part.safetensors';shard.write_bytes(b'original fixture bytes')
            manifest = {'files': {p.name: check_assets.digest(p) for p in [index, shard]}}
            self.assertEqual(check_assets.verify(root, manifest)['weight_shards'], 1)
            shard.write_bytes(b'changed fixture bytes')
            with self.assertRaises(ValueError):check_assets.verify(root, manifest)

    def test_asset_manifest_must_cover_shards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);index = root / 'model.safetensors.index.json'
            index.write_text(json.dumps({'weight_map': {'weight': 'part.safetensors'}}))
            with self.assertRaises(ValueError):
                check_assets.verify(root, {'files': {index.name: check_assets.digest(index)}})

    def test_cli_reports_incompatible_baseline_as_failure(self):
        q, p = reports()
        env = {'packages': {}, 'model': q['model'], 'model_config_sha256': 'config',
               'weights_index_sha256': 'weights', 'physical_devices': '0,1'}
        base = baseline_report(q, p, {**env, 'physical_devices': '2,3'})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = {'quality': q, 'performance': p, 'environment': env, 'source': {}, 'baseline': base}
            cmd = [sys.executable, str(ROOT / 'tests/score.py'), '--output', str(root / 'output')]
            for key, value in values.items():
                path = root / (key + '.json');path.write_text(json.dumps(value));cmd.extend(['--' + key, str(path)])
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(json.loads((root / 'output/summary.json').read_text())['status'], 'INVALID')
            self.assertEqual(json.loads((root / 'output/summary.json').read_text())['score'], 0.0)
            self.assertEqual(float((root / 'output/reward.txt').read_text()), 0.0)

    def test_baseline_protocol(self):
        q, p = reports(); score.validate(q, p)
        self.assertEqual(score.compare(q, p, q, p)['score'], 1)

    def test_acceptance_uses_16_requests(self):
        q, p = reports()
        self.assertEqual(performance.DEFAULTS['requests'], 16)
        self.assertEqual(performance.DEFAULTS['concurrency'], 16)
        for case in p['cases']:
            self.assertEqual(case['pooled']['completed_requests'], 48)
            self.assertTrue(all(r['completed_requests'] == 16 for r in case['rounds']))
        score.validate(q, p)

    def test_legacy_workloads_cannot_score(self):
        for count in (32, 64):
            with self.subTest(requests=count):
                q, p = reports()
                p['contract']['workload'].update(requests=count, concurrency=count)
                with self.assertRaises(ValueError):score.validate(q, p)

    def test_incomplete_request_count_cannot_score(self):
        q, p = reports();p['cases'][0]['rounds'][0]['completed_requests'] = 15
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_improvement_accounting(self):
        q, p = reports(); candidate = copy.deepcopy(p)
        for case in candidate['cases']:
            for row in [*case['rounds'], case['pooled']]:
                row['duration_s'] /= 1.1
                for k in ['total_throughput_tok_s', 'output_throughput_tok_s', 'request_throughput_req_s']:row[k] *= 1.1
        self.assertAlmostEqual(score.compare(q, candidate, q, p)['score'], 1.1)

    def test_cli_preserves_continuous_scores_and_quality_gate(self):
        q, p = reports()
        env = {'packages': {}, 'model': q['model'], 'model_config_sha256': 'config',
               'weights_index_sha256': 'weights', 'physical_devices': '0,1'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / 'baseline.json'
            base.write_text(json.dumps(baseline_report(q, p, env)))
            for name, speed, good_quality, status, reward in [
                    ('noop', 1.0, True, 'VALID', 1.0),
                    ('regressed', 0.95, True, 'VALID', 0.95),
                    ('small-gain', 1.02, True, 'VALID', 1.02),
                    ('faster', 1.5, True, 'VALID', 1.5),
                    ('incorrect', 1.1, False, 'INVALID', None)]:
                candidate, quality = copy.deepcopy(p), copy.deepcopy(q)
                for case in candidate['cases']:
                    for row in [*case['rounds'], case['pooled']]:
                        row['duration_s'] /= speed
                        for key in ('total_throughput_tok_s', 'output_throughput_tok_s', 'request_throughput_req_s'):
                            row[key] *= speed
                if not good_quality:
                    quality['results'][0]['passed'] = False
                out = root / name
                cmd = [sys.executable, str(ROOT / 'tests/score.py'), '--output', str(out), '--baseline', str(base)]
                for key, value in {'quality': quality, 'performance': candidate, 'environment': env, 'source': {}}.items():
                    path = root / (name + '-' + key + '.json')
                    path.write_text(json.dumps(value));cmd.extend(['--' + key, str(path)])
                proc = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0 if reward is not None else 1)
                self.assertEqual(json.loads((out / 'summary.json').read_text())['status'], status)
                record = json.loads((out / 'summary.json').read_text())
                if reward is None:self.assertEqual(record['score'], 0.0)
                else:self.assertAlmostEqual(record['score'], reward)
                self.assertEqual(record['valid'], reward is not None)
                self.assertEqual(float((out / 'reward.txt').read_text()), json.loads((out / 'summary.json').read_text())['score'])

    def test_different_quality_cases(self):
        q, p = reports();other = copy.deepcopy(q);other["results"][0]["id"] = "foreign"
        with self.assertRaises(ValueError):score.compare(other, p, q, p)

    def test_wrong_model_cannot_score(self):
        q, p = reports();q['model'] = p['model'] = 'Qwen3.6-35B-A3B'
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_bad_quality_cannot_score(self):
        q, p = reports(); q['results'][0]['passed'] = False
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_legacy_quality_subset_cannot_score(self):
        q, p = reports()
        q.update(total=72, passed=72, results=q['results'][:72])
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_response_coverage_cannot_drop_or_duplicate_cases(self):
        suite, _, _ = evaluate.load_suite(ROOT / 'tests/quality100')
        rows = [{'id': c['id'], 'category': c['category']} for c in suite['cases']]
        for wrong in (rows[:-1], rows + [rows[0]]):
            with self.assertRaises(ValueError):evaluate.validate_rows(wrong, suite['cases'])

    def test_invalid_deadline_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, deadline in enumerate(('0', '-1', 'nan', 'inf')):
                out = root / str(index)
                cmd = [sys.executable, str(ROOT / 'tests/score.py'), '--output', str(out),
                       '--deadline', deadline]
                for key in ('quality', 'performance', 'environment', 'source'):
                    cmd.extend(['--' + key, str(root / 'not-read.json')])
                result = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads((out / 'summary.json').read_text())['status'], 'INVALID')
                self.assertEqual(json.loads((out / 'summary.json').read_text())['score'], 0.0)
                self.assertEqual(float((out / 'reward.txt').read_text()), json.loads((out / 'summary.json').read_text())['score'])

    def test_smoke_cannot_score(self):
        q, p = reports();p['contract']['workload']['requests'] = 1
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_reduced_state_precision(self):
        q, p = reports();p['server_info']['mamba_ssm_dtype'] = 'float16'
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_immutable_serving_config_cannot_change(self):
        for key, value in [('context_length', 66560), ('tp_size', 4),
                           ('disable_radix_cache', False), ('disable_cuda_graph', True),
                           ('speculative_algorithm', 'EAGLE')]:
            with self.subTest(field=key):
                q, p = reports();p['server_info'][key] = value
                with self.assertRaises(ValueError):score.validate(q, p)

    def test_incomplete_matrix(self):
        q, p = reports();p['cases'].pop()
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_token_shortcut(self):
        q, p = reports();p['cases'][0]['rounds'][0]['output_tokens'] -= 1
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_nan_metrics(self):
        q, p = reports();p['cases'][0]['pooled']['total_throughput_tok_s'] = float('nan')
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_fabricated_summary(self):
        q, p = reports();p['cases'][0]['pooled']['total_throughput_tok_s'] *= 2
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_pooled_duration_cannot_fabricate_speedup(self):
        q, p = reports();row = p['cases'][0]['pooled'];row['duration_s'] /= 2
        for key in ('total_throughput_tok_s', 'output_throughput_tok_s', 'request_throughput_req_s'):
            row[key] *= 2
        with self.assertRaises(ValueError):score.validate(q, p)

    def test_raw_measurement_audit(self):
        _, p = reports()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in p['cases']:
                case['excluded_attempts'] = [0]
                for attempt in range(4):
                    rows = [{'index': i, 'status': 'SUCCEEDED', 'input_tokens': case['input_length'],
                             'output_tokens': 1024, 'ttft_ms': 1.0, 'tpot_ms': 2.0} for i in range(16)]
                    record = {'requests': rows, 'duration_s': 10.0, 'compile_changes': 0,
                              'accepted': attempt > 0}
                    (root / f"{case['input_length']}-attempt-{attempt}.json").write_text(json.dumps(record))
            verify.validate_raw_measurements(root, p)
            path = root / '1024-attempt-1.json';original = json.loads(path.read_text())
            for label in ('compile', 'requests', 'timing'):
                record = copy.deepcopy(original)
                if label == 'compile':record['compile_changes'] = 1
                elif label == 'requests':record['requests'].pop()
                else:record['duration_s'] = 5
                path.write_text(json.dumps(record))
                with self.subTest(fault=label):
                    with self.assertRaises(ValueError):verify.validate_raw_measurements(root, p)
            path.write_text(json.dumps(original));path.unlink()
            with self.assertRaises(ValueError):verify.validate_raw_measurements(root, p)

    def test_empty_compiler_cache_is_not_a_failure(self):
        # Accounting-only control, not a substitute for a native performance run.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cache=root/'cache';cache.mkdir()
            args=SimpleNamespace(output=root/'output',base_url='http://localhost:30000/v1',model='Qwen3.6-27B',
                                 responses=None,baseline=None,max_throughput_drop_pct=0,timeout=10,
                                 api_key_env=None,compile_cache=[cache])
            info={'model_path':'/models/Qwen3.6-27B','served_model_name':'Qwen3.6-27B',
                  'tp_size':2,'disable_radix_cache':True,'disable_cuda_graph':False,
                  'speculative_algorithm':None,'dtype':'bfloat16','context_length':67584}
            def batch(url,inputs,config,timeout,key):
                return ([{'index':i,'status':'SUCCEEDED','input_tokens':len(ids),
                          'output_tokens':1024,'ttft_ms':1.0,'tpot_ms':2.0} for i,ids in enumerate(inputs)],10.0)
            with patch.object(performance,'DEFAULTS',{**performance.DEFAULTS,'input_lengths':[1024]}), patch.object(performance,'server_info',return_value=info), patch.object(performance,'batch',side_effect=batch):
                self.assertEqual(performance.run(args,evaluate,emit=False),0)
            self.assertEqual(len(json.loads((root/'output/summary.json').read_text())['cases'][0]['rounds']),3)

    def test_local_deadline_does_not_compare_remote_clock(self):
        q,p=reports()
        env={'packages':{},'model':q['model'],'model_config_sha256':'c',
             'weights_index_sha256':'w','physical_devices':'0,1'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=root/'base.json';base.write_text(json.dumps(baseline_report(q,p,env)))
            for name,offset,seconds,status in [('remote-ahead',86400,120,'VALID'),
                                              ('remote-behind',-86400,120,'VALID'),
                                              ('local-expired',86400,-1,'LATE')]:
                values={'quality':q,'performance':p,'environment':{**env,'started_at':time.time()+offset},'source':{}}
                cmd=[sys.executable,str(ROOT/'tests/score.py'),'--baseline',str(base),
                     '--deadline',str(time.time()+seconds),'--output',str(root/name)]
                for key,value in values.items():
                    path=root/(name+'-'+key+'.json');path.write_text(json.dumps(value));cmd+=['--'+key,str(path)]
                proc=subprocess.run(cmd,capture_output=True,text=True)
                value=json.loads((root/name/'summary.json').read_text())
                self.assertEqual(proc.returncode,0 if status=='VALID' else 1)
                self.assertEqual(value['status'],status)
                self.assertIsInstance(value['score'],float)
                self.assertEqual(value['score'],1.0 if status=='VALID' else 0.0)
                self.assertEqual(float((root/name/'reward.txt').read_text()),value['score'])

    def test_failed_request_not_dropped(self):
        with self.assertRaises(ValueError):performance.summarize([{'status': 'FAILED'}], 1)

    def test_suite_is_complete(self):
        suite, oracles, protocol = evaluate.load_suite(ROOT / 'tests/quality100')
        self.assertEqual(len(suite['cases']), 100)
        self.assertEqual(len(oracles), 100)
        self.assertEqual(Counter(c['category'] for c in suite['cases']),
                         {'code': 40, 'math': 35, 'instruction_following': 25})
        self.assertEqual(len({(c['source']['repository'], c['source']['original_id'])
                              for c in suite['cases']}), 100)
        selection = json.loads((ROOT / 'tests/quality100/selection.json').read_text())
        self.assertEqual(len(selection['preserved_ids']), 72)
        self.assertEqual(len(selection['added_ids']), 28)
        self.assertFalse(set(selection['preserved_ids']) & set(selection['added_ids']))
        self.assertEqual(set(selection['preserved_ids'] + selection['added_ids']), set(oracles))

    def test_parallel_language_checks_are_repeatable(self):
        suite_root = ROOT / 'tests/quality100'
        suite, oracles, protocol = evaluate.load_suite(suite_root)
        checker, _ = evaluate.load_verifier(suite_root, protocol)
        case = next(c for c in suite['cases'] if c['id'] == 'I22')
        examples = [('what are the two young boys carrying?', True),
                    ('bonjour je parle français et je visite la ville de paris avec mes amis.', False)] * 10
        def grade(example):
            text, expected = example
            row = {'request_status': 'SUCCEEDED', 'output': text,
                   'metadata': {'finish_reason': 'stop', 'completion_tokens': 10}}
            return evaluate.grading.evaluate(case, oracles[case['id']], row, checker)['passed'], expected
        with ThreadPoolExecutor(max_workers=4) as pool:
            for actual, expected in pool.map(grade, examples):
                self.assertEqual(actual, expected)

    def test_quality_output_budget_cannot_be_ignored(self):
        suite, oracles, _ = evaluate.load_suite(ROOT / 'tests/quality100')
        case = next(c for c in suite['cases'] if c['id'] == 'M31')
        for tokens, expected in [(10, 'PASS'), (1025, 'OUTPUT_BUDGET_EXCEEDED'), (None, 'RESPONSE_ERROR')]:
            row = {'request_status': 'SUCCEEDED', 'output': 'FINAL_ANSWER: ' + oracles['M31']['expected'],
                   'metadata': {'finish_reason': 'stop', 'completion_tokens': tokens}}
            result = evaluate.grading.evaluate(case, oracles['M31'], row, None)
            self.assertEqual(result['status'], expected)


if __name__ == '__main__':unittest.main()
