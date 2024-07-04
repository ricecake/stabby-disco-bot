#!/bin/env python
import argparse
from stabby import grammar

parser = argparse.ArgumentParser()
parser.add_argument('filename', help="Path of the grammar file to be used")
parser.add_argument('root_symbol', default='ROOT', help="The symbol to start with")
args = parser.parse_args()

language = grammar.Grammar(args.filename)

for i in range(0, 25):
    print(language.generate(start=args.root_symbol))
