"""Validate public chunk construction without loading vLLM or a GPU."""

from collections import abc
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import NotRequired, TypedDict
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from streaming_input_adapter import chunk_factory


def public_generate(element_type):
    async def generate(prompt):
        yield prompt

    generate.__annotations__["prompt"] = str | abc.AsyncIterator[element_type]
    return generate


class InputAdapterTests(unittest.TestCase):
    def test_keyword_only_optional_field_before_prompt(self):
        @dataclass(kw_only=True)
        class Chunk:
            sampling_params: object = None
            prompt: str

        value = chunk_factory(public_generate(Chunk))("hello")
        self.assertIsInstance(value, Chunk)
        self.assertEqual(value.prompt, "hello")
        self.assertIsNone(value.sampling_params)

    def test_optional_positional_fields_preserve_defaults(self):
        default = object()

        class Chunk:
            def __init__(self, metadata=default, prompt=""):
                self.metadata, self.prompt = metadata, prompt

        value = chunk_factory(public_generate(Chunk))("hello")
        self.assertEqual(value.prompt, "hello")
        self.assertIs(value.metadata, default)

    def test_positional_only_prompt_after_optional_metadata(self):
        default = object()

        class Chunk:
            def __init__(self, metadata=default, prompt="", /):
                self.metadata, self.prompt = metadata, prompt

        value = chunk_factory(public_generate(Chunk))("hello")
        self.assertEqual(value.prompt, "hello")
        self.assertIs(value.metadata, default)

    def test_renamed_required_input_after_optional_metadata(self):
        @dataclass(kw_only=True)
        class Chunk:
            metadata: object = None
            content: str

        value = chunk_factory(public_generate(Chunk))("hello")
        self.assertEqual(value.content, "hello")
        self.assertIsNone(value.metadata)

    def test_single_positional_input(self):
        class Chunk:
            def __init__(self, content, /):
                self.content = content

        self.assertEqual(chunk_factory(public_generate(Chunk))("hello").content,
                         "hello")

    def test_raw_text_and_typed_dictionary(self):
        class Chunk(TypedDict):
            metadata: NotRequired[str]
            content: str

        text = chunk_factory(public_generate(str))("hello")
        self.assertIs(type(text), str)
        self.assertEqual(text, "hello")
        self.assertEqual(chunk_factory(public_generate(Chunk))("hello"),
                         {"content": "hello"})

    def test_unannotated_duck_typed_input(self):
        async def generate(prompt):
            yield prompt

        value = chunk_factory(generate)("hello")
        self.assertEqual(value, "hello")
        self.assertEqual(value.prompt, "hello")
        self.assertIsNone(value.sampling_params)

    def test_constructor_runs_once_and_errors_propagate(self):
        calls = []

        class Chunk:
            def __init__(self, *, metadata=None, prompt):
                calls.append((metadata, prompt))
                raise ValueError("invalid content")

        factory = chunk_factory(public_generate(Chunk))
        self.assertEqual(calls, [])
        with self.assertRaisesRegex(ValueError, "invalid content"):
            factory("hello")
        self.assertEqual(calls, [(None, "hello")])


if __name__ == "__main__":
    unittest.main()
