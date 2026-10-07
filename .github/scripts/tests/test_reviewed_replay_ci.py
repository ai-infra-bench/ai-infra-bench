"""Reviewed case dispatch: no implicit profiles or stale curator inputs."""
import argparse
from contextlib import redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import task_ci


class ReviewedReplayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.task = self.root / 'example'
        tools = self.task / 'validation/tools'
        tools.mkdir(parents=True)
        (self.task / 'validation/patches').mkdir()
        (self.task / 'task.toml').write_text('[environment]\nworkdir="/workspace/pi"\ngpus=0\n')
        def ref(name, content):
            (tools / name).write_text(content)
            return {'path': 'tools/' + name, 'sha256': hashlib.sha256(content.encode()).hexdigest()}
        self.profile = {'binding': ref('interface.py', 'class Binding: pass\n'),
                        'scenario': ref('scenario.py', 'class Scenario: pass\n'),
                        'review_evidence': ref('review.json', '{"review":"explicit contract"}\n')}
        (self.task / 'validation/patches/control.patch').write_text('control\n')
        self.manifest = {
            'schema_version': 'ai_infra_bench_validation_cases.v2',
            'cases': [{'name':'control', 'patch':'patches/control.patch',
                       'patch_sha256':hashlib.sha256(b'control\n').hexdigest(),
                       'expected_reward':0,'apply_after':'oracle'}],
            'reviewed_replay': {'runner':ref('replay.py', '# trusted replay\n'),
                                'cases':{name:copy.deepcopy(self.profile) for name in ('base','oracle','control')}}}
        self.save()

    def save(self):
        (self.task / 'validation/ci-cases.json').write_text(json.dumps(self.manifest))

    def test_every_known_case_has_an_explicit_profile(self):
        self.assertEqual(task_ci.validation_manifest(self.task), self.manifest)
        for name in ('base','oracle','control'):
            broken = copy.deepcopy(self.manifest)
            del broken['reviewed_replay']['cases'][name]
            with self.subTest(name=name), self.assertRaises(task_ci.ContractError):
                task_ci.reviewed_replay_config(self.task, broken)
        self.manifest['reviewed_replay']['cases']['unknown'] = self.profile
        with self.assertRaises(task_ci.ContractError):
            task_ci.reviewed_replay_config(self.task, self.manifest)

    def test_changed_adapter_symlink_and_escape_are_rejected(self):
        for target in ('../interface.py','tools/../interface.py','/tmp/interface.py'):
            broken=copy.deepcopy(self.manifest)
            broken['reviewed_replay']['cases']['base']['binding']['path']=target
            with self.subTest(path=target), self.assertRaises(task_ci.ContractError):
                task_ci.reviewed_replay_config(self.task,broken)
        adapter=self.task/'validation/tools/interface.py'
        adapter.write_text('changed')
        with self.assertRaises(task_ci.ContractError):
            task_ci.validation_manifest(self.task)
        adapter.unlink()
        outside=self.root/'outside.py'; outside.write_text('class Binding: pass\n')
        adapter.symlink_to(outside)
        with self.assertRaises(task_ci.ContractError):
            task_ci.validation_manifest(self.task)

    def test_absent_opt_in_keeps_ordinary_case_inventory(self):
        del self.manifest['reviewed_replay']; self.save()
        self.assertIsNone(task_ci.reviewed_replay_config(self.task,self.manifest))
        capture=io.StringIO()
        with patch.object(task_ci,'TASKS_DIR',self.root), patch.object(task_ci,'task_contract'), redirect_stdout(capture):
            task_ci.command_cases(argparse.Namespace(task='example'))
        self.assertEqual(json.loads(capture.getvalue()),[
            {'name':'base','expected_reward':0},{'name':'oracle','expected_reward':1},
            {'name':'control','expected_reward':0}])

    def test_case_filter_is_explicit_and_rejects_unknown_or_repeated_names(self):
        with patch.object(task_ci,'TASKS_DIR',self.root), patch.object(task_ci,'task_contract'):
            for value in ('','oracle,oracle','missing','oracle,'):
                with self.subTest(value=value), self.assertRaises(task_ci.ContractError):
                    task_ci.command_cases(argparse.Namespace(task='example',filter=value))
            capture=io.StringIO()
            with redirect_stdout(capture):
                task_ci.command_cases(argparse.Namespace(task='example',filter='control,base'))
            self.assertEqual([c['name'] for c in json.loads(capture.getvalue())],['base','control'])
            self.assertTrue(all(c['reviewed_replay'] for c in json.loads(capture.getvalue())))

    def fake_run(self, argv, **kwargs):
        output=Path(argv[argv.index('--output')+1]); job=output/'jobs/reviewed-replay'
        job.mkdir(parents=True); (output/'task').mkdir()
        (output/'task/task.toml').write_text('artifacts=[]\n')
        # The CI wrapper must reject a successful runner with the wrong reward.
        reward=getattr(self,'observed_reward',0)
        (job/'result.json').write_text(json.dumps({'stats':{'n_completed_trials':1,'n_errored_trials':0,
            'evals':{'test':{'reward_stats':{'reward':{str(reward):['trial']}}}}}}))
        return subprocess.CompletedProcess(argv,0)

    def run_case(self, name):
        args=argparse.Namespace(task='example',image='sha256:'+'a'*64,case=name,
                                output=str(self.root/('out-'+name)),override_cpus=4)
        with patch.object(task_ci,'TASKS_DIR',self.root), patch.object(task_ci,'validate_task'), \
             patch.object(task_ci.subprocess,'run',side_effect=self.fake_run) as run:
            task_ci.command_run_reviewed_case(args)
        return run.call_args.args[0]

    def test_dispatch_honors_patch_base_resources_and_expected_reward(self):
        argv=self.run_case('control')
        self.assertIn('--after-oracle',argv)
        self.assertEqual(argv[argv.index('--submission')+1],str(self.task/'validation/patches/control.patch'))
        for flag,value in [('--cpus','limit'),('--memory','limit'),('--override-cpus','4')]:
            self.assertEqual(argv[argv.index(flag)+1],value)
        self.assertTrue({'--no-artifacts','--delete'}<=set(argv))
        self.assertEqual(argv[argv.index('--binding')+1],str(self.task/'validation/tools/interface.py'))
        self.assertTrue((self.root/'out-control/jobs/reviewed-replay/prepared-task.toml').is_file())
        with self.assertRaises(task_ci.ContractError):
            self.run_case('oracle')  # fake runner completed, but reward 0 != 1

    def test_unknown_submission_cannot_fall_back_to_reference(self):
        with self.assertRaises(task_ci.ContractError):
            self.run_case('new-model')

    def test_inline_inputs_preserve_bytes_and_are_removed_after_dispatch(self):
        expected = {}
        profile = self.manifest['reviewed_replay']['cases']['control']
        for field, content in [('scenario', {'candidate_files': {'entry.ts': 'a' * 64}}),
                               ('review_evidence', {'review': 'explicit contract'})]:
            expected[field] = (json.dumps(content, indent=2) + '\n').encode()
            profile[field] = {'content': content,
                              'sha256': hashlib.sha256(expected[field]).hexdigest()}
        self.save()
        original_run = self.fake_run
        paths = []
        def inspect_run(argv, **kwargs):
            for field in expected:
                path = Path(argv[argv.index('--' + field.replace('_', '-')) + 1])
                self.assertEqual(path.read_bytes(), expected[field])
                paths.append(path)
            return original_run(argv, **kwargs)
        self.fake_run = inspect_run
        self.run_case('control')
        self.assertTrue(paths)
        self.assertTrue(all(not path.exists() for path in paths))

    def test_inline_inputs_reject_stale_hash_empty_data_and_inline_code(self):
        content = {'review': 'explicit contract'}
        reference = {'content': content,
                     'sha256': hashlib.sha256((json.dumps(content, indent=2) + '\n').encode()).hexdigest()}
        for field, invalid in [('scenario', dict(reference, sha256='0' * 64)),
                               ('review_evidence', dict(reference, content={})),
                               ('review_evidence', dict(reference, path='tools/review.json')),
                               ('binding', reference)]:
            broken = copy.deepcopy(self.manifest)
            broken['reviewed_replay']['cases']['control'][field] = invalid
            with self.subTest(field=field, invalid=invalid), self.assertRaises(task_ci.ContractError):
                task_ci.reviewed_replay_config(self.task, broken)

    def test_gpu_opt_in_cannot_bypass_leasing(self):
        (self.task/'task.toml').write_text('[environment]\ngpus=1\n')
        with self.assertRaises(task_ci.ContractError):
            task_ci.validation_manifest(self.task)

    def test_partial_matrix_cannot_publish(self):
        import os
        script=Path(task_ci.__file__).with_name('run_task_validation.sh')
        env=dict(os.environ,TASK_NAME='example',TARGET_PLATFORM='linux/amd64',
                 PUBLISH_IMAGE='true',AI_INFRA_CASE_FILTER='oracle')
        result=subprocess.run(['bash',str(script)],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertIn('complete case matrix',result.stderr)

if __name__=='__main__': unittest.main()
