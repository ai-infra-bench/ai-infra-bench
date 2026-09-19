"""Construct chunks from the public generate annotation and constructor."""

from collections import abc
import inspect
import typing


class PromptValue(str):
    """Text also usable by an unannotated duck-typed prompt interface."""

    @property
    def prompt(self):
        return str(self)

    sampling_params = None


def _constructor_factory(declared):
    try:
        signature = inspect.signature(declared)
    except (TypeError, ValueError):
        return None
    parameters = [parameter for parameter in signature.parameters.values()
                  if parameter.kind not in (parameter.VAR_POSITIONAL,
                                            parameter.VAR_KEYWORD)]
    selected = next((p for p in parameters if p.name == "prompt"), None)
    if selected is None:
        required = [p for p in parameters if p.default is p.empty]
        if len(required) == 1:
            selected = required[0]
        elif len(parameters) == 1:
            selected = parameters[0]
        else:
            return None

    # Bind without calling candidate code. Optional metadata keeps its defaults,
    # and constructor errors from an actual chunk must propagate to the caller.
    marker = object()
    try:
        if selected.kind == selected.POSITIONAL_ONLY:
            preceding = parameters[:parameters.index(selected)]
            if any(p.default is p.empty for p in preceding):
                return None
            defaults = tuple(p.default for p in preceding)
            signature.bind(*defaults, marker)
            return lambda prompt: declared(*defaults, prompt)
        signature.bind(**{selected.name: marker})
    except TypeError:
        return None
    return lambda prompt: declared(**{selected.name: prompt})


def chunk_factory(generate):
    """Use the declared public element type, never a prescribed symbol or module."""
    try:
        annotation = typing.get_type_hints(generate).get("prompt")
    except (NameError, TypeError, AttributeError):
        annotation = None

    def element(value):
        origin = typing.get_origin(value)
        if origin in (abc.AsyncGenerator, abc.AsyncIterable, abc.AsyncIterator):
            return typing.get_args(value)[0]
        for arg in typing.get_args(value):
            found = element(arg)
            if found is not None:
                return found
        return None

    declared = element(annotation)
    if declared is str:
        return str
    if typing.is_typeddict(declared):
        required = list(declared.__required_keys__)
        if len(required) == 1:
            return lambda prompt: {required[0]: prompt}
    if (inspect.isclass(declared) and declared not in (str, dict, object)
            and not typing.is_typeddict(declared)):
        factory = _constructor_factory(declared)
        if factory is not None:
            return factory
    return PromptValue
