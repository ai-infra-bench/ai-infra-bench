"""Exercise task configuration at the generated Dockerfile boundary."""
import importlib.util
import hashlib
import contextlib
import io
import os
import re
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TEMPLATE_DIR = Path(__file__).resolve().parents[1]
ROOT = TEMPLATE_DIR.parents[1]
spec = importlib.util.spec_from_file_location("pi_generate", TEMPLATE_DIR / "generate.py")
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)
spec = importlib.util.spec_from_file_location("pi_build", TEMPLATE_DIR / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
NODE_22_23 = "node:22.23.2-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5"


class GenerateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.task = Path(self.tmp.name) / "task"
        (self.task / "environment").mkdir(parents=True)
        source = ROOT / "tasks/pi-context-management"
        shutil.copyfile(source / "task.toml", self.task / "task.toml")
        shutil.copytree(source / "environment/lock", self.task / "environment/lock")
        self.config = self.task / "environment/pi-template.json"
        self.output = self.task / "environment/Dockerfile"

    def render(self):
        return generate.render(self.task, generate.TEMPLATE_PATH.read_text())[1]

    def test_existing_tasks_still_render_byte_for_byte(self):
        # Catches default substitutions that silently invalidate unchanged tasks.
        for name in ("pi-background-processes", "pi-agent-trace"):
            with self.subTest(task=name):
                task = ROOT / "tasks" / name
                output, actual = generate.render(task, generate.TEMPLATE_PATH.read_text())
                self.assertEqual(output.read_bytes(), actual.encode())

    def test_config_preserves_node_runtime_and_agent_ownership(self):
        # Catches ignored runtime configuration and incomplete user substitution.
        self.config.write_text(json.dumps({"node_image": NODE_22_23, "agent_user": "agent"}))
        actual = self.render()
        self.assertIn("FROM " + NODE_22_23 + "\n", actual)
        self.assertIn("RUN useradd --create-home --shell /bin/bash agent\n", actual)
        self.assertIn("RUN chown -R agent:agent /workspace/pi", actual)
        self.assertIn("install -d -o agent -g agent -m 0755", actual)
        self.assertIn("install -d -o agent -g agent /tmp/pi-baseline-home", actual)
        self.assertIn("su agent -c 'cd /workspace/pi", actual)
        self.assertIn("su -p agent -s /bin/bash", actual)
        self.assertNotRegex(actual, r"(?:chown -R|install -d -o|su(?: -p)?) node(?:[: ])")
        self.assertIn("node ../../node_modules/vitest/vitest.mjs run --retry 2", actual)
        self.assertIn("RUN --network=none npm run build:offline", actual)
        self.assertIn("chown -R root:root /opt/pi-baseline", actual)
        self.assertIn("chmod -R go-w /opt/pi-baseline", actual)
        self.assertNotRegex(actual, r"(?m)^COPY (?!--from=|<<)")
        self.assertNotIn("__PI_", actual)

    def test_source_cli_sets_loader_only_for_pi_and_preserves_arguments(self):
        self.config.write_text(json.dumps({"node_image": NODE_22_23, "agent_user": "agent", "source_cli": True}))
        actual=self.render()
        match=re.search(r"COPY --chown=0:0 --chmod=0755 <<'PI_SOURCE_CLI_EOF' /usr/local/bin/pi\n(.*?)\nPI_SOURCE_CLI_EOF",actual,re.S)
        self.assertIsNotNone(match)
        self.assertNotRegex(actual,r"(?m)^ENV (?:NODE_OPTIONS|TSX_TSCONFIG_PATH)=")
        wrapper=Path(self.tmp.name)/"pi"
        wrapper.write_text(match.group(1)+"\n");wrapper.chmod(0o755)
        node=Path(self.tmp.name)/"node"
        node.write_text("#!"+sys.executable+"\nimport json,os,sys\nprint(json.dumps({'argv':sys.argv[1:],'node_options':os.environ.get('NODE_OPTIONS'),'tsconfig':os.environ.get('TSX_TSCONFIG_PATH')}))\n")
        node.chmod(0o755)
        env=dict(os.environ,PATH=str(Path(self.tmp.name))+os.pathsep+os.environ['PATH'],NODE_OPTIONS='inherited-options',TSX_TSCONFIG_PATH='inherited-config')
        result=subprocess.run([str(wrapper),'two words','--test=value'],env=env,check=True,capture_output=True,text=True)
        value=json.loads(result.stdout)
        self.assertEqual(value['argv'],['/workspace/pi/packages/coding-agent/src/cli.ts','two words','--test=value'])
        self.assertEqual(value['node_options'],'--import=/workspace/pi/node_modules/tsx/dist/loader.mjs')
        self.assertEqual(value['tsconfig'],'/workspace/pi/tsconfig.json')
        self.assertEqual(env['NODE_OPTIONS'],'inherited-options')
        self.assertEqual(env['TSX_TSCONFIG_PATH'],'inherited-config')

    def test_source_cli_requires_a_json_boolean(self):
        for bad in ('true',1,0,None,[],{}):
            with self.subTest(source_cli=bad):
                self.config.write_text(json.dumps({"node_image":NODE_22_23,"agent_user":"agent","source_cli":bad}))
                with self.assertRaisesRegex(ValueError,'source_cli must be a boolean'):
                    self.render()

    def test_explicitly_disabled_source_cli_keeps_default_dockerfile_bytes(self):
        source=ROOT/'tasks/pi-background-processes'
        shutil.copyfile(source/'task.toml',self.task/'task.toml')
        shutil.copytree(source/'environment/lock',self.task/'environment/lock',dirs_exist_ok=True)
        self.config.write_text(json.dumps({'source_cli':False}))
        self.assertEqual(self.render().encode(),(source/'environment/Dockerfile').read_bytes())

    def test_npm_ignore_scripts_renders_the_frozen_install_policy(self):
        self.config.write_text(json.dumps({'node_image':NODE_22_23,'agent_user':'agent','npm_ignore_scripts':True}))
        self.assertIn(' && npm ci --ignore-scripts --no-audit --no-fund',self.render())
        for bad in ('true',1,0,None,[],{}):
            with self.subTest(npm_ignore_scripts=bad):
                self.config.write_text(json.dumps({'node_image':NODE_22_23,'agent_user':'agent','npm_ignore_scripts':bad}))
                with self.assertRaisesRegex(ValueError,'npm_ignore_scripts must be a boolean'):
                    self.render()

    def test_lock_manifest_records_configured_npm_install_policy(self):
        sys.path.insert(0,str(TEMPLATE_DIR))
        self.addCleanup(lambda:sys.path.remove(str(TEMPLATE_DIR)))
        spec=importlib.util.spec_from_file_location('pi_lock',TEMPLATE_DIR/'lock.py')
        lock=importlib.util.module_from_spec(spec);spec.loader.exec_module(lock)
        original=(self.task/'environment/lock/package-lock.json').read_text()
        def git_boundary(args,**kwargs):
            return subprocess.CompletedProcess(args,0,stdout=original if 'show' in args else '')
        for ignore_scripts,want in ((False,'npm (npm ci --no-audit --no-fund)'),(True,'npm (npm ci --ignore-scripts --no-audit --no-fund)')):
            with self.subTest(ignore_scripts=ignore_scripts):
                self.config.write_text(json.dumps({'node_image':NODE_22_23,'agent_user':'agent','npm_ignore_scripts':ignore_scripts}))
                with patch.object(lock.subprocess,'run',side_effect=git_boundary),contextlib.redirect_stdout(io.StringIO()):
                    lock.generate(self.task)
                manifest=json.loads((self.task/'environment/lock/manifest.json').read_text())
                self.assertEqual(manifest['resolver'],want)
                self.assertEqual((self.task/'environment/lock/package-lock.json').read_text(),original)

    def test_source_workspace_keeps_validation_without_claiming_a_dist_build(self):
        self.config.write_text(json.dumps({'node_image':NODE_22_23,'agent_user':'agent','source_cli':True,'npm_ignore_scripts':True,'workspace_mode':'source'}))
        actual=self.render()
        self.assertNotIn('npm run build:offline',actual)
        self.assertNotIn('test -f packages/coding-agent/dist/index.js',actual)
        self.assertIn('node packages/ai/scripts/check-model-data.ts',actual)
        self.assertIn('test -z "$(git status --porcelain)"',actual)
        self.assertIn('test/path-utils.test.ts',actual)
        self.assertIn('vitest/vitest.mjs run --retry 2 --reporter=junit',actual)
        self.assertIn('ALLOWED_ENVIRONMENTAL_FAILURES = 6',actual)
        self.assertIn('packages/ai/src/providers/data/[^/]+[.]json$',actual)
        self.assertIn(' -ge 40',actual)
        self.assertNotIn(' -gt 500',actual)
        self.assertIn('LABEL ai.infra.bench.workspace-mode=source',actual)
        self.assertIn('COPY --chown=0:0 --chmod=0755',actual)
        self.assertIn(' && pi --version',actual)
        self.assertLess(actual.index('COPY --chown=0:0 --chmod=0755'),actual.index('# Agent-phase view:'))
        loader='ENV NODE_OPTIONS=--import=/workspace/pi/node_modules/tsx/dist/loader.mjs'
        tsconfig='ENV TSX_TSCONFIG_PATH=/workspace/pi/tsconfig.json'
        self.assertIn(loader,actual)
        self.assertIn(tsconfig,actual)
        self.assertLess(actual.index(loader),actual.index('node packages/ai/scripts/check-model-data.ts'))
        self.assertLess(actual.index(tsconfig),actual.index('vitest/vitest.mjs run --retry 2 --reporter=junit'))

    def test_source_workspace_rejects_missing_compatibility_options(self):
        for cli,ignore in ((False,True),(True,False),(False,False)):
            with self.subTest(source_cli=cli,npm_ignore_scripts=ignore):
                self.config.write_text(json.dumps({'node_image':NODE_22_23,'agent_user':'agent','workspace_mode':'source','source_cli':cli,'npm_ignore_scripts':ignore}))
                with self.assertRaisesRegex(ValueError,'source requires source_cli and npm_ignore_scripts'):
                    self.render()
        for mode in ('other',True,None,0):
            self.config.write_text(json.dumps({'node_image':NODE_22_23,'agent_user':'agent','workspace_mode':mode}))
            with self.assertRaisesRegex(ValueError,'workspace_mode must be prebuilt or source'):
                self.render()

    def test_source_build_record_labels_itself_as_source(self):
        self.config.write_text(json.dumps({'node_image':NODE_22_23,'agent_user':'agent','source_cli':True,'npm_ignore_scripts':True,'workspace_mode':'source'}))
        self.output.write_text(self.render())
        output=self.build_with_docker_boundary(True)
        record=json.loads(next(line[6:] for line in output.splitlines() if line.startswith('IMAGE ')))
        self.assertEqual(record['workspace_mode'],'source')
        self.assertFalse(record['dist_built'])
        self.assertEqual(record['installed_versions']['pi'],'0.85.1 (workspace source)')

    def test_invalid_config_never_overwrites_dockerfile(self):
        # Catches silent unknown keys, type coercion, unpinned images and shell injection.
        bad = [
            [], None, {"extra": "ignored"}, {"agent_user": "root"},
            {"agent_user": "agent; id"}, {"agent_user": False},
            {"node_image": "node:22"}, {"node_image": NODE_22_23 + "\nRUN id"},
            {"node_image": 42},
        ]
        for config in bad:
            with self.subTest(config=config):
                self.config.write_text(json.dumps(config))
                self.output.write_text("do not replace\n")
                proc = subprocess.run([sys.executable, str(TEMPLATE_DIR / "generate.py"), str(self.task)], capture_output=True, text=True)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(self.output.read_text(), "do not replace\n")

    def test_config_image_must_agree_with_lock_provenance(self):
        # Catches a runtime change hidden behind a stale lock manifest.
        self.config.write_text(json.dumps({"node_image": NODE_22_23, "agent_user": "agent"}))
        manifest_path = self.task / "environment/lock/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["node_image"] = "node:22.19.0-bookworm-slim@sha256:4a4884e8a44826194dff92ba316264f392056cbe243dcc9fd3551e71cea02b90"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "node_image"):
            self.render()

    def test_account_must_match_task_candidate_user(self):
        # Catches an image whose writable checkout belongs to the wrong user.
        self.config.write_text(json.dumps({"node_image": NODE_22_23, "agent_user": "node"}))
        with self.assertRaisesRegex(ValueError, "agent.*user"):
            self.render()

    def test_retained_manifest_includes_optional_generation_input(self):
        # Catches losing configuration provenance despite a valid rendered image.
        for configured in (False, True):
            with self.subTest(configured=configured):
                if configured:
                    self.config.write_text(json.dumps({"node_image": NODE_22_23, "agent_user": "agent"}))
                else:
                    self.config.unlink(missing_ok=True)
                    source = ROOT / "tasks/pi-background-processes"
                    shutil.copyfile(source / "task.toml", self.task / "task.toml")
                    shutil.copytree(source / "environment/lock", self.task / "environment/lock", dirs_exist_ok=True)
                if configured:
                    source = ROOT / "tasks/pi-context-management"
                    shutil.copyfile(source / "task.toml", self.task / "task.toml")
                    shutil.copytree(source / "environment/lock", self.task / "environment/lock", dirs_exist_ok=True)
                self.output.write_text(self.render())
                self.build_with_docker_boundary(configured)
                manifest = json.loads((self.task / "environment/image-manifest.json").read_text())
                expected = {"Dockerfile", "lock/package-lock.json", "lock/manifest.json"}
                if configured:
                    expected.add("pi-template.json")
                    self.assertEqual(manifest["files"].get("pi-template.json"), hashlib.sha256(self.config.read_bytes()).hexdigest())
                self.assertEqual(set(manifest["files"]), expected)

    def build_with_docker_boundary(self, configured, during_build=None):
        metadata, _ = build.load_task(self.task)
        source_mode=self.config.is_file() and json.loads(self.config.read_text()).get("workspace_mode")=="source"

        def docker_boundary(*args, capture=False):
            # Only Docker is replaced: generator checks and manifest I/O run for real.
            if args[0] != "docker":
                return subprocess.run(args, check=True, capture_output=True, text=True)
            if args[1:3] == ("buildx", "build"):
                self.assertEqual(list(Path(args[-1]).iterdir()), [])
                if during_build is not None:
                    during_build()
                value = ""
            elif args[1:3] == ("image", "inspect"):
                value = [{"Id": "sha256:" + "a" * 64, "Os": "linux", "Architecture": "amd64", "Config": {"Labels": {
                    "ai.infra.bench.base-commit": metadata["metadata"]["base_commit"],
                    "ai.infra.bench.dependency-cutoff": metadata["metadata"]["dependency_cutoff"],
                    "ai.infra.bench.environment-template": "pi-harbor-node",
                    **({"ai.infra.bench.workspace-mode":"source"} if source_mode else {}),
                }}}]
            elif args[1] == "run":
                value = {
                    "node": "22.23.2" if configured else "22.19.0",
                    "npm": "10.9.3", "fd": "10.2.0", "ripgrep": "13.0.0",
                    "python3": "3.11.2", "git": "2.39.5", "pi": "0.85.1",
                    "baseline": {"totals": {"tests": 2500, "failures": 0, "errors": 0, "skipped": 0}, "failed_on_base": []},
                }
            else:
                self.fail(f"unexpected external call: {args}")
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(value))

        output=io.StringIO()
        with patch.object(build, "run", side_effect=docker_boundary), contextlib.redirect_stdout(output):
            build.build(self.task, "linux/amd64")
        return output.getvalue()

    def test_config_modified_during_build_does_not_replace_retained_manifest(self):
        # Catches a completed image being attributed to inputs changed mid-build.
        self.config.write_text(json.dumps({"node_image": NODE_22_23, "agent_user": "agent"}))
        self.output.write_text(self.render())
        retained = self.task / "environment/image-manifest.json"
        retained.write_text("previous verified manifest\n")
        before = self.config.read_bytes()

        def change_config():
            self.config.write_text(json.dumps({"node_image": NODE_22_23, "agent_user": "node"}))

        with self.assertRaisesRegex(RuntimeError, "inputs changed"):
            self.build_with_docker_boundary(True, during_build=change_config)
        self.assertNotEqual(self.config.read_bytes(), before)
        self.assertEqual(retained.read_text(), "previous verified manifest\n")


if __name__ == "__main__":
    unittest.main()
