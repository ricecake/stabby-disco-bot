import re
from typing import Iterable, Text, Optional

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


def prettify_params(params) -> str:
    filtered_kwargs = [
        (key, value) for key, value in params.items() if value is not None and value != ''
    ]

    display = []
    for key, value in filtered_kwargs:
        display_key = key.replace('_', ' ').capitalize()
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


def template_grammar_fill(input: dict[str, Optional[str]], grammar: stabby.grammar.Grammar, fill: bool = True) -> dict[str, str]:
    output = dict()
    for field, value in input.items():
        if value is not None:
            output[field] = value
        elif fill:
            output[field] = grammar.generate(start=field.capitalize())
    return output
