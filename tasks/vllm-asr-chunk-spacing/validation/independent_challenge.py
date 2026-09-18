"""Independent public-boundary examples, outside the grading inventory."""
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from speech_harness import run_public_speech_request


async def main():
    inputs = [
        ("supplementary-han", None, [("𠀀甲2026",), ("",), ('"乙𠀁"',)], '𠀀甲2026"乙𠀁"'),
        ("katakana-with-number", None, [("ﾃｽﾄ2026",), ('"ﾂﾂﾞｷ"',)], 'ﾃｽﾄ2026"ﾂﾂﾞｷ"'),
        ("english-quoted-clause", "en", [("We finished 'phase one.'",), ("Continue now.",)], "We finished 'phase one.' Continue now."),
        ("existing-tab", None, [("The status\t",), ("is healthy.",)], "The status\tis healthy."),
    ]
    results = []
    for name, language, chunks, expected in inputs:
        for stream in (False, True):
            result = await run_public_speech_request(
                "transcription", stream, language, chunks
            )
            results.append({"case": name, "stream": stream,
                            "expected": expected, "result": asdict(result),
                            "passed": result.text == expected and (not stream or result.done)})
    output = Path("/logs/verifier/independent-result.json")
    output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    assert len(results) == 8 and all(result["passed"] for result in results), results
    print("Independent challenge: 8/8 passed")


if __name__ == "__main__":
    asyncio.run(main())
