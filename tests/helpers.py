from typing import Any, Callable, Sequence, Tuple, List, Dict, Text, overload
from functools import wraps
from inspect import signature
import unittest

import collections.abc


CaseTupleSequence = Sequence[Tuple[Any, ...]]
CaseDictSequence = Sequence[Dict[Text, Any]]
CaseTupleFunc = Callable[[], CaseTupleSequence]
CaseDictFunc = Callable[[], CaseDictSequence]
CaseType = CaseTupleSequence | CaseDictSequence | CaseTupleFunc | CaseDictFunc

@overload
def expand_test_cases(cases: CaseTupleSequence, f: Callable) -> Sequence[Dict[Text, Any]]:
    ...
@overload
def expand_test_cases(cases: CaseDictSequence, f: Callable) -> Sequence[Dict[Text, Any]]:
    ...
@overload
def expand_test_cases(cases: CaseTupleFunc, f: Callable) -> Sequence[Dict[Text, Any]]:
    ...
@overload
def expand_test_cases(cases: CaseDictFunc, f: Callable) -> Sequence[Dict[Text, Any]]:
    ...
def expand_test_cases(cases: CaseType, f) -> Sequence[Dict[Text, Any]]:
    match cases:
        case collections.abc.Callable():
            gen_cases = cases()
            return expand_test_cases(gen_cases)  # type: ignore
        case [Tuple(), *_]:
            sig = signature(f)

            formatted_cases = []
            for case in cases:
                formatted_cases.append({
                    arg: value
                    for arg, value in list(zip([arg for arg in sig.parameters if arg != 'self'], case))
                })

            return formatted_cases
        case [Dict(), *_]:
            return cases
        case _:
            raise Exception()


@overload
def with_params(description: Text, cases: List[Tuple]) -> Callable:
    ...
@overload
def with_params(description: Text, cases: List[Dict[Text, Any]]) -> Callable:
    ...
@overload
def with_params(description: Text, cases: Callable[[], List[Tuple]]) -> Callable:
    ...
@overload
def with_params(description: Text, cases: Callable[[], List[Dict[Text, Any]]]) -> Callable:
    ...

def with_params(description, cases) -> Callable:
    def decorator(f: Callable) -> Callable:
        params = expand_test_cases(cases, f)

        @wraps(f)
        def wrapper(self: unittest.TestCase, *args, **kwargs):
            for case in params:
                with self.subTest(description, **case):
                    return f(self, *args, **{**case, **kwargs})
        return wrapper
    return decorator
