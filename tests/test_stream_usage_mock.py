"""Offline tests of the actual analyzer stream methods, without importing API dependencies."""
import ast
import logging
import types
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Tuple


class _LiteLLMStreamError(Exception):
    def __init__(self, message, partial_received=False):
        super().__init__(message)
        self.partial_received = partial_received


def load_methods():
    source = Path(__file__).resolve().parents[1] / 'src' / 'analyzer.py'
    module = ast.parse(source.read_text(encoding='utf-8'))
    selected = []
    for node in ast.walk(module):
        if isinstance(node, (ast.ClassDef,)):
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name in (
                    '_consume_litellm_stream', '_normalize_usage'
                ):
                    selected.append(method)
    if len(selected) != 2:
        raise AssertionError(f'Expected 2 methods in analyzer.py, found {len(selected)}')
    module_ast = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module_ast)
    namespace = {
        'Any': Any, 'Dict': Dict, 'List': List, 'Optional': Optional,
        'Callable': Callable, 'Tuple': Tuple,
        '_LiteLLMStreamError': _LiteLLMStreamError,
        'logger': logging.getLogger('stream-mock-test'),
    }
    exec(compile(module_ast, str(source), 'exec'), namespace)
    return namespace


class StreamUsageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        methods = load_methods()
        cls.normalize = staticmethod(methods['_normalize_usage'])
        cls.consume = staticmethod(methods['_consume_litellm_stream'])

    def make_subject(self):
        subject = types.SimpleNamespace()
        subject._normalize_usage = types.MethodType(self.normalize, subject)
        subject._extract_stream_text = lambda chunk: chunk.get('text', '')
        return subject

    def test_stream_usage(self):
        subject = self.make_subject()
        chunks = [
            {'text': 'hello ', 'usage': None},
            {'text': 'world', 'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}},
        ]
        text, usage = self.consume(subject, chunks, model='mock-model')
        self.assertEqual(text, 'hello world')
        self.assertEqual(usage['total_tokens'], 120)

    def test_final_usage_only_chunk(self):
        subject = self.make_subject()
        chunks = [
            {'text': 'answer', 'usage': None},
            {'text': '', 'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}},
        ]
        text, usage = self.consume(subject, chunks, model='mock-model')
        self.assertEqual(text, 'answer')
        self.assertEqual(usage['total_tokens'], 15)

    def test_missing_usage(self):
        subject = self.make_subject()
        text, usage = self.consume(subject, [{'text': 'ok', 'usage': None}], model='mock-model')
        self.assertEqual(text, 'ok')
        self.assertEqual(usage, {})

    def test_interrupted_stream(self):
        subject = self.make_subject()
        def broken():
            yield {'text': 'partial', 'usage': None}
            raise RuntimeError('connection dropped')
        with self.assertRaises(_LiteLLMStreamError) as caught:
            self.consume(subject, broken(), model='mock-model')
        self.assertTrue(caught.exception.partial_received)


if __name__ == '__main__':
    unittest.main()
