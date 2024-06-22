from typing import Any, Callable, Iterable, Tuple, List, Dict, Text, overload
from functools import wraps
from inspect import signature
import unittest


@overload
def expand_test_cases(cases: Iterable[Tuple], f: Callable) -> List[Dict[Text, Any]]:
    ...
@overload
def expand_test_cases(cases: Iterable[Dict[Text, Any]], f: Callable) -> List[Dict[Text, Any]]:
    ...
@overload
def expand_test_cases(cases: Callable[[], Iterable[Tuple]], f: Callable) -> List[Dict[Text, Any]]:
    ...
@overload
def expand_test_cases(cases: Callable[[], Iterable[Dict[Text, Any]]], f: Callable) -> List[Dict[Text, Any]]:
    ...
def expand_test_cases(cases, f) -> List[Dict[Text, Any]]:
    if callable(cases):
        gen_cases = list(cases())
        return expand_test_cases(gen_cases)  # type: ignore
    elif isinstance(cases[0], dict):
        return cases

    sig = signature(f)

    formated_cases = []
    for case in cases:
        formated_cases.append({
            arg: value
            for arg, value in list(zip([arg for arg in sig.parameters if arg != 'self'], case))
        })

    return formated_cases

@overload
def with_params(description: Text, cases: Iterable[Tuple]) -> Callable:
    ...
@overload
def with_params(description: Text, cases: Iterable[Dict[Text, Any]]) -> Callable:
    ...
@overload
def with_params(description: Text, cases: Callable[[], Iterable[Tuple]]) -> Callable:
    ...
@overload
def with_params(description: Text, cases: Callable[[], Iterable[Dict[Text, Any]]]) -> Callable:
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
