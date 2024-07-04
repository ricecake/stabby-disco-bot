import re
import random


class Grammar():
    def __init__(self, grammar_definition) -> None:
        grammar = open(grammar_definition)

        lines = grammar.readlines()
        rules = []
        non_terminal: dict = {}  # stores total of odds of non-terminal symbol which is the key
        for line in lines:
            if line != '\n' and line[0] != '#':
                l_tokens = line.split()
                for token in l_tokens:
                    # ignore comments in grammar
                    if '#' in token:
                        l_tokens = l_tokens[0:l_tokens.index(token)]
                        break
                rules.append(l_tokens)
                # calculate cumulative probabilities
                if l_tokens[1] not in non_terminal.keys():
                    non_terminal[l_tokens[1]] = float(l_tokens[0])
                else:
                    non_terminal[l_tokens[1]] += float(l_tokens[0])

        self.rules = rules
        self.non_terminal = non_terminal

    def _sentence_generator(self, symbol, sentence) -> None:
        rand_count = {}  # stores rule as value, key is the cumulative probability of the rule
        # for writing tree structure
        # base case
        if symbol not in self.non_terminal.keys():
            sentence.append(symbol)
        else:
            total_count = float(self.non_terminal[symbol])
            current_count = 0.0
            # find all rules applicable for given non-terminal symbol
            for rule in self.rules:
                if rule[1] == symbol:
                    current_count = current_count + float(rule[0]) / total_count
                    rand_count[current_count] = rule
            r = random.random()
            apply_rule = []
            # select rule according to the number generated and probabilities calculated
            for prob in sorted(rand_count.keys()):
                if prob >= r:
                    apply_rule = rand_count[prob]
                    break
            for s in apply_rule[2:len(apply_rule)]:
                # extra space for bracket
                self._sentence_generator(s, sentence)

    def generate(self, start='ROOT') -> str:
        sentence: list = []
        self._sentence_generator(start, sentence)
        text = ' '.join(sentence)
        text = re.sub(r'[ ]+', ' ', text)
        text = re.sub(r',([ ]*,)+', ',', text)
        text = re.sub(r'[,]+', ',', text)
        text = re.sub(r'([\[({])\s+', r'\1', text)
        text = re.sub(r'\s+([\])},])', r'\1', text)
        text = re.sub(r'([\w\d])\s+([^\w\d])', r'\1\2', text)
        return text
