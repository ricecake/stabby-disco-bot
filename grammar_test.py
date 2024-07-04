#!/bin/env python
import argparse
import re
from stabby import grammar, text_utils

parser = argparse.ArgumentParser()
parser.add_argument('filename', help="Path of the grammar file to be used")
subparsers = parser.add_subparsers(dest='subcommand')
subparsers.required = True

maker_parser = subparsers.add_parser('maker')
test_parser = subparsers.add_parser('test')

test_parser.add_argument('root_symbol', default='ROOT', help="The symbol to start with")
args = parser.parse_args()

language = grammar.Grammar(args.filename)

if args.subcommand == 'test':
    for i in range(0, 25):
        print(language.generate(start=args.root_symbol))
elif args.subcommand == 'maker':
    params = dict(
        subject=None,
        object=None,
        action=None,
        perspective=None,
        quality=None,
        medium=None,
        style=None,
        lighting=None,
        environment=None,
        color=None,
        mood=None,
        texture=None,
        time_period=None,
        cultural_elements=None,
        emotion=None,
        skin_texture=None,
    )

    prompt = text_utils.template_grammar_fill(params, language, True)

    prompt_text = ''
    for joint_fields in [
        ['subject', 'object', 'action'],
        ['perspective', 'quality', 'medium', 'style'],
    ]:
        prompt_text += ' '.join([prompt.pop(field, '') for field in joint_fields])
        prompt_text += ', '

    prompt_text += ', '.join([v for v in prompt.values() if v])
    prompt_text = re.sub(r',(\s*,)+', ',', prompt_text)
    print(prompt_text)
