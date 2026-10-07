#!/usr/bin/env python3
"""Self-check verifier report validation with intentionally malformed reports."""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from check_junit import inspect
from check_pass_to_pass import KNOWN_BASE_CASE, KNOWN_BASE_SIGNATURE, compare, observed_known_base_failures, outcomes

class Integrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.path = Path(self.temp.name) / 'result.xml'
        self.names = ['case one', 'case two']
    def tearDown(self): self.temp.cleanup()
    def document(self, names=None, **attrs):
        root = ET.Element('testsuites'); suite = ET.SubElement(root, 'testsuite', tests='2', failures='0', errors='0', skipped='0')
        suite.attrib.update(attrs)
        for name in self.names if names is None else names: ET.SubElement(suite, 'testcase', name=name, classname='test.ts')
        ET.ElementTree(root).write(self.path); return root
    def test_accepts_complete_report(self):
        self.document(); self.assertTrue(inspect(self.path, self.names)['passed']); self.assertEqual(len(outcomes(self.path)), 2)
        original = outcomes(self.path)
        root = ET.parse(self.path).getroot(); suite = root.find('testsuite'); suite.set('tests', '3')
        ET.SubElement(suite, 'testcase', name='intentionally replaced', classname='test/plan-mode-extension.test.ts')
        ET.ElementTree(root).write(self.path)
        self.assertEqual(outcomes(self.path), original)
    def test_rejects_early_exit_duplicate_skip_and_false_totals(self):
        for names, attrs in [([], {}), (['case one'], {}), (['case one', 'case one'], {}), (None, {'tests': '99'}), (None, {'skipped': '1'})]:
            self.document(names, **attrs); self.assertFalse(inspect(self.path, self.names)['passed'])
        root = self.document(); ET.SubElement(root.find('.//testcase'), 'skipped'); ET.ElementTree(root).write(self.path)
        self.assertFalse(inspect(self.path, self.names)['passed'])
    def test_baseline_parser_rejects_duplicates_and_aggregate_errors(self):
        for names, attrs in [(['case one', 'case one'], {}), (None, {'tests': '99'}), (None, {'failures': '1'})]:
            self.document(names, **attrs)
            with self.assertRaises(ValueError): outcomes(self.path)

    def test_original_passed_cases_never_allow_failure_skip_or_omission(self):
        base = {"required": "passed", "skip": "skipped", "known Base failure": "failed"}
        self.assertTrue(compare(base, base)["passed"])
        self.assertTrue(compare(base, {**base, "known Base failure": "passed"})["passed"])
        for current in [{**base, "required": "failed"}, {**base, "required": "skipped"}, {k:v for k,v in base.items() if k != "required"}]:
            self.assertFalse(compare(base, current)["passed"])

    def test_known_base_failure_requires_exact_assertion_and_stack(self):
        key = KNOWN_BASE_CASE; classname, name = key.split("::", 1)
        pins = {"allowed_environmental_failures": [{**KNOWN_BASE_SIGNATURE, "evidence": [{"path": "retained.xml", "sha256": "a" * 64}]}]}
        def document(message=KNOWN_BASE_SIGNATURE["failure_message"], failure_type="AssertionError", stack=KNOWN_BASE_SIGNATURE["stack_contains"], extra=None, observed_name=name, repeats=1):
            root = self.document([observed_name], tests="1", failures="1")
            case = root.find(".//testcase"); case.set("classname", classname)
            for _ in range(repeats):
                failure = ET.SubElement(case, "failure", type=failure_type, message=message); failure.text = "AssertionError\n ❯ " + stack
            if extra:
                other = ET.SubElement(case, extra, type="AssertionError", message="another assertion"); other.text = stack
            ET.ElementTree(root).write(self.path)
            return observed_known_base_failures(self.path, pins)
        self.assertEqual(document(), {key})
        self.assertEqual(document(repeats=3), {key})
        for args in [dict(message="other assertion"), dict(failure_type="Error"), dict(stack="test/auth-storage.test.ts:99:1"), dict(message="Test timed out", failure_type="Error"), dict(extra="failure"), dict(extra="error"), dict(extra="skipped"), dict(observed_name="another case"), dict(repeats=4)]:
            self.assertEqual(document(**args), set())
        self.document([], tests="0"); self.assertEqual(observed_known_base_failures(self.path, pins), set())
        invalid = {"allowed_environmental_failures": [{**KNOWN_BASE_SIGNATURE, "case": "another case"}]}
        with self.assertRaises(ValueError): observed_known_base_failures(self.path, invalid)

    def test_known_base_failure_never_allows_other_regressions(self):
        key = KNOWN_BASE_CASE; base = {key: "passed", "another case": "passed"}; current = {**base, key: "failed"}
        self.assertFalse(compare(base, current)["passed"])
        self.assertTrue(compare(base, current, [key])["passed"])
        self.assertFalse(compare(base, {**current, "another case": "failed"}, [key])["passed"])
        self.assertFalse(compare(base, {**current, "another case": "skipped"}, [key])["passed"])
        for changed in [{**base, key: "skipped"}, {"another case": "passed"}]:
            with self.assertRaises(ValueError): compare(base, changed, [key])
        with self.assertRaises(ValueError): compare(base, current, ["another case"])

if __name__ == '__main__': unittest.main()
