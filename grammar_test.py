import random, argparse

class Grammar():
    def __init__(self, grammar_definition) -> None:
        grammar = open(grammar_definition)

        lines = grammar.readlines()
        rules=[]
        non_terminal={} #stores total of odds of non-terminal symbol which is the key
        for l in lines:
            if l!='\n' and l[0]!='#':
                l_tokens = l.split()
                for token in l_tokens:
                    #ignore comments in grammar
                    if '#' in token:
                        l_tokens=l_tokens[0:l_tokens.index(token)]
                        break
                rules.append(l_tokens)
                #calculate cumulative probabilities
                if l_tokens[1] not in non_terminal.keys():
                    non_terminal[l_tokens[1]] = float(l_tokens[0])
                else:
                    non_terminal[l_tokens[1]] += float(l_tokens[0])

        self.rules = rules
        self.non_terminal = non_terminal

    def _sentence_generator(self, symbol, sentence) -> None:
        rand_count={}           #stores rule as value, key is the cumulative probability of the rule
        #for writing tree structure
        #base case
        if symbol not in self.non_terminal.keys():
            sentence.append(symbol)
        else:
            total_count = float(self.non_terminal[symbol])
            current_count=0
            #find all rules applicable for given non-terminal symbol
            for rule in self.rules:
                if rule[1]==symbol:
                    current_count = current_count + float(rule[0])/total_count
                    rand_count[current_count] = rule
            r = random.random()
            apply_rule = []
            #select rule according to the number generated and probabilities calculated
            for prob in sorted(rand_count.keys()):
                if prob >= r:
                    apply_rule = rand_count[prob]
                    break
            for s in apply_rule[2:len(apply_rule)]:
                self._sentence_generator(s, sentence)  #extra space for bracket

    def generate(self) -> str:
        sentence = []
        self._sentence_generator('ROOT', sentence)
        return ' '.join(sentence)


parser = argparse.ArgumentParser()
parser.add_argument('filename', help="Path of the grammar file to be used")
args = parser.parse_args()

grammar = Grammar(args.filename)

for i in range(0, 25):
    print(grammar.generate())