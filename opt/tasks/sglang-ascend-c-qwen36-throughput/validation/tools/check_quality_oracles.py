"""Check all frozen oracles with positive/negative controls, not model inference."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
import evaluate
import grading

assert Path(grading.__file__).resolve().is_relative_to(ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--code-image', default=grading.DEFAULT_IMAGE)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a fresh control report path')
    suite_root = ROOT / 'tests/quality100'
    suite, oracles, protocol = evaluate.load_suite(suite_root)
    verifier, _ = evaluate.load_verifier(suite_root, protocol)
    witnesses = json.loads((Path(__file__).with_name('quality_witnesses.json')).read_text())['cases']

    def check(case):
        oracle = oracles[case['id']]
        assert case['oracle_sha256'] == hashlib.sha256(json.dumps(oracle, sort_keys=True).encode()).hexdigest()
        if case['category'] == 'code':
            positive = oracle['reference_code']
            negative = f"def {oracle['entrypoint']}(*args, **kwargs):\n    return None\n"
        elif case['category'] == 'math':
            positive = 'FINAL_ANSWER: ' + str(oracle['expected'])
            negative = 'FINAL_ANSWER: ' + str(Decimal(str(oracle['expected']).replace(',', '')) + 1)
        else:
            positive = witnesses[case['id']]['passing']
            negative = witnesses[case['id']]['failing']
        def grade(text, finish='stop'):
            # This token count is a synthetic fixture, not a tokenizer/model measurement.
            row = {'request_status': 'SUCCEEDED', 'output': text,
                   'metadata': {'finish_reason': finish, 'completion_tokens': 1}}
            return grading.evaluate(case, oracle, row, verifier, image=args.code_image)
        good, bad, truncated = grade(positive), grade(negative), grade(positive, 'length')
        return {'id': case['id'], 'category': case['category'], 'positive': good, 'negative': bad,
                'truncated': truncated,
                'passed': good['passed'] and not bad['passed'] and bad['status'] not in evaluate.ERROR_STATUSES
                          and truncated['status'] == 'TRUNCATED'}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(check, suite['cases']))
    result = {'scope': 'Oracle and grader controls only; no model inference.',
              'total': len(rows), 'passed': sum(r['passed'] for r in rows),
              'categories': dict(Counter(r['category'] for r in rows)), 'results': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'results'}))
    for row in rows:
        if not row['passed']:
            print(json.dumps(row, ensure_ascii=False))
    return 0 if result['total'] == result['passed'] == 100 else 1


if __name__ == '__main__':
    raise SystemExit(main())
