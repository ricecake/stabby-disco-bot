import builtins
import re
from typing import Any, Iterable, Mapping, Text, Optional, Union, cast

import stabby
import stabby.grammar


def prompt_to_overlay(prompt):

    prompt = re.sub(r':\s*[+-]?\d+(?:\.\d*)?\s*(?=[\)\]])', '', prompt)  # handle attention modifiers
    prompt = re.sub(r'[ ]+', ' ', prompt)

    for c in '[]()':
        prompt = prompt.replace(c, '')

    parts = prompt.split(',', 1)
    title = " ".join(parts[0].split())
    title = title.title()

    desc = ""
    if len(parts) > 1:
        desc = " ".join(parts[1].split())
        desc = ', '.join([phrase.strip().capitalize() for phrase in desc.split(',')])
    return (title, desc)


def filter_params(params: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in params.items()
        if value is not None and value != ''
    }

def prettify_param(param) -> str:
    return param.replace('_', ' ').capitalize()

def prettify_params(params) -> str:
    display = []
    for key, value in filter_params(params).items():
        display_key = prettify_param(key)
        display.append('{}: {}'.format(display_key, value))

    return ', '.join(display)


def tokenize_prompt(prompt: Optional[str]) -> list[str]:
    if prompt is None:
        return []
    return [s.strip() for s in prompt.split(',')]


def rejoin_prompt_tokens(tokens: Optional[Iterable[Text]]) -> Optional[Text]:
    if tokens is None or not tokens:
        return None
    return ', '.join(tokens)


def union_prompts(first: Optional[str], second: Optional[str]) -> Optional[str]:
    first_tokens = tokenize_prompt(first)
    second_tokens = tokenize_prompt(second)

    return rejoin_prompt_tokens(dict.fromkeys(first_tokens + second_tokens))


def subtract_prompts(first: Optional[str], second: Optional[str]) -> Optional[str]:
    first_tokens = tokenize_prompt(first)
    second_tokens = tokenize_prompt(second)

    base_set = dict.fromkeys(first_tokens)
    for remove in second_tokens:
        base_set.pop(remove, None)

    return rejoin_prompt_tokens(base_set)


def apply_default_params(request_params: dict, default_params: dict) -> dict:
    new_params = request_params.copy()
    for field, value in default_params.items():
        if new_params.get(field) is None:
            new_params[field] = value

    return new_params


def template_grammar_fill(input: Mapping[str, Optional[str]], grammar: stabby.grammar.Grammar, fill: bool = True) -> dict[str, str]:
    output = dict()
    for field, value in input.items():
        if value is not None:
            output[field] = value
        elif fill:
            output[field] = grammar.generate(start=field.capitalize())
    return output

def convert_to_bool(input: Union[bool, str, int, float]) -> bool:
    match type(input):
        case builtins.bool:
            return cast(bool, input)
        case builtins.str:
            to_check = cast(str, input).lower()
            is_text_affirmative = to_check in ['true', 'yes']
            is_text_negative = to_check in ['false', 'no', "none", '']
            is_special_number_affirmative = input in ['1']
            is_special_number_negative = input in ['0', '-1']

            if is_text_affirmative or is_special_number_affirmative:
                return True
            elif is_text_negative or is_special_number_negative:
                return False
            elif to_check.isdecimal():
                return bool(int(input))
            else:
                return bool(input)
        case builtins.int | builtins.float:
            if input == -1:
                return False
            else:
                return bool(input)
        case _:
            return bool(input)
