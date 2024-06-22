import unittest

from stabby import generation
from tests.helpers import with_params


class TestGeneration(unittest.TestCase):

    @with_params('Prompt test cases', [
        ('test', 'Test', ''),
        ('test the thing', 'Test The Thing', ''),
        ('test               thing', 'Test Thing', ''),
        ('test the thing, other thing', 'Test The Thing', 'Other thing'),
        ('test the thing, other thing, yet again', 'Test The Thing', 'Other thing, Yet again'),
        ('TEST THING, OTHER THING, YET AGAIN', 'Test The Thing', 'Other thing', 'Yet again'),
    ])
    def test_gen_description(self, prompt, title, description):
        got_title, got_description = generation.gen_description(prompt)
        self.assertEqual(got_title, title)
        self.assertEqual(got_description, description)
