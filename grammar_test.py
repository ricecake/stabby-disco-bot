import argparse
from stabby import grammar

parser = argparse.ArgumentParser()
parser.add_argument('filename', help="Path of the grammar file to be used")
args = parser.parse_args()

language = grammar.Grammar(args.filename)

for i in range(0, 25):
    print(language.generate())
